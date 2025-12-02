#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests",
#     "PyGithub",
#     "anthropic",
#     "jsonschema",
#     "pydantic",
#     "python-slugify",
#     "tenacity",
# ]
# ///
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from anthropic import Anthropic, APIError
from github import Github, GithubException
from jsonschema import validate as jsonschema_validate
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from pydantic import BaseModel, Field
from slugify import slugify
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

IMAGE_STATE_FILE = Path(".image_state")
MAX_IMAGE_NUMBER = 49

REPO_CONFIG: Dict[str, Dict[str, str]] = {
    "zenml-io/zenml": {
        "type": "oss",
        "markdown_file": "gitbook-release-notes/oss.md",
        "default_branch": "main",
        "audience": "oss",
    },
    "zenml-io/zenml-dashboard": {
        "type": "oss",
        "markdown_file": "gitbook-release-notes/oss.md",
        "default_branch": "main",
        "audience": "oss",
    },
    "zenml-io/zenml-cloud-ui": {
        "type": "pro",
        "markdown_file": "gitbook-release-notes/pro.md",
        "default_branch": "main",
        "audience": "pro",
    },
    "zenml-io/zenml-cloud-api": {
        "type": "pro",
        "markdown_file": "gitbook-release-notes/pro.md",
        "default_branch": "develop",
        "audience": "pro",
    },
}

LABEL_MAPPING: Dict[str, str] = {
    "bug": "bugfix",
    "bugfix": "bugfix",
    "fix": "bugfix",
    "feature": "feature",
    "enhancement": "improvement",
    "improvement": "improvement",
    "deprecation": "deprecation",
    "breaking": "deprecation",
}


class ChangelogLabel(str, Enum):
    BUGFIX = "bugfix"
    DEPRECATION = "deprecation"
    IMPROVEMENT = "improvement"
    FEATURE = "feature"


class Audience(str, Enum):
    PRO = "pro"
    OSS = "oss"
    ALL = "all"


class ChangelogCopy(BaseModel):
    title: str = Field(..., max_length=60, description="Clear, user-facing title without PR number")
    description: str = Field(..., description="1-3 sentences explaining the user-facing value, markdown allowed")
    suggested_labels: List[ChangelogLabel] = Field(default_factory=list, description="Suggested labels based on the PR content")


class MarkdownSection(BaseModel):
    content: str = Field(..., description="Complete markdown section for the release notes")


anthropic_client: Optional[Anthropic] = None





def get_next_image_number() -> int:
    current = 0
    if IMAGE_STATE_FILE.exists():
        try:
            current = int(IMAGE_STATE_FILE.read_text().strip() or "0")
        except ValueError:
            current = 0
    next_num = (current % MAX_IMAGE_NUMBER) + 1
    IMAGE_STATE_FILE.write_text(str(next_num))
    return next_num


def find_previous_tag(gh: Github, repo_name: str, current_tag: str) -> Optional[str]:
    repo = gh.get_repo(repo_name)
    releases = list(repo.get_releases())
    if not releases:
        return None
    releases_sorted = sorted(
        releases,
        key=lambda r: (r.published_at or r.created_at or datetime.min.replace(tzinfo=timezone.utc)),
    )
    tag_index = next((i for i, rel in enumerate(releases_sorted) if rel.tag_name == current_tag), None)
    if tag_index is None:
        raise RuntimeError(f"Release tag {current_tag} not found in {repo_name}")
    if tag_index == 0:
        return None
    return releases_sorted[tag_index - 1].tag_name


def _release_date(repo, tag: str) -> datetime:
    release = repo.get_release(tag)
    published = release.published_at or release.created_at
    if not published:
        raise RuntimeError(f"Release {tag} in {repo.full_name} has no published/created date")
    if not published.tzinfo:
        published = published.replace(tzinfo=timezone.utc)
    return published


def get_release_prs(gh: Github, repo_name: str, since_tag: Optional[str], until_tag: str) -> List[Dict[str, Any]]:
    repo = gh.get_repo(repo_name)
    config = REPO_CONFIG[repo_name]
    until_date = _release_date(repo, until_tag)
    since_date = _release_date(repo, since_tag) if since_tag else datetime(2020, 1, 1, tzinfo=timezone.utc)
    query = (
        f"repo:{repo_name} is:pr is:merged label:release-notes "
        f"base:{config['default_branch']} "
        f"merged:{since_date.strftime('%Y-%m-%dT%H:%M:%SZ')}..{until_date.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )
    search_results = gh.search_issues(query)
    prs: List[Dict[str, Any]] = []
    for issue in search_results:
        pr = repo.get_pull(issue.number)
        if not pr.merged_at:
            continue
        prs.append(
            {
                "number": pr.number,
                "title": pr.title,
                "url": pr.html_url,
                "author": pr.user.login if pr.user else "unknown",
                "body": pr.body or "",
                "labels": [label.name for label in pr.labels],
                "merged_at": pr.merged_at,
            }
        )
    prs.sort(key=lambda pr_item: pr_item["merged_at"])
    return prs


def slugify_title(title: str) -> str:
    return slugify(title)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(APIError),
)
def llm_generate_changelog_copy(pr_title: str, pr_body: str, pr_url: str, repo_type: str) -> ChangelogCopy:
    if anthropic_client is None:
        raise RuntimeError("Anthropic client not initialized")
    audience = "open source users" if repo_type == "oss" else "ZenML Pro users"
    response = anthropic_client.beta.messages.parse(
        model="claude-sonnet-4-5-20250514",
        betas=["structured-outputs-2025-11-13"],
        max_tokens=700,
        temperature=0,
        output_format=ChangelogCopy,
        messages=[
            {
                "role": "user",
                "content": (
                    "You are writing changelog entries for ZenML, an MLOps platform.\n\n"
                    f"PR Title: {pr_title}\n"
                    f"PR URL: {pr_url}\n"
                    f"PR Body:\n{pr_body[:3500]}\n\n"
                    f"The audience is {audience}. Focus on what users can now do or benefit from.\n"
                    "Generate a concise title (max 60 characters, no PR number), a 1-3 sentence markdown-friendly "
                    "description, and suggest appropriate labels."
                ),
            }
        ],
    )
    return response.parsed_output


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(APIError),
)
def llm_generate_markdown_section(
    prs: List[Dict[str, Any]],
    release_tag: str,
    release_url: str,
    published_at: str,
    repo_type: str,
    source_repo: str,
    image_number: int,
) -> str:
    if anthropic_client is None:
        raise RuntimeError("Anthropic client not initialized")
    pr_summaries = "\n".join(
        f"- {pr['title']} (#{pr['number']}): {pr['url']} — {pr['body'][:300].replace(chr(10), ' ')}"
        for pr in prs
    )
    include_links_instruction = (
        "Include a markdown link to each PR using the format [PR #<number>](<url>) for each bullet."
        if repo_type == "oss"
        else "Do not include PR links; keep the prose concise for Pro audiences."
    )
    response = anthropic_client.beta.messages.parse(
        model="claude-sonnet-4-5-20250514",
        betas=["structured-outputs-2025-11-13"],
        max_tokens=2000,
        temperature=0,
        output_format=MarkdownSection,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Write release notes for repository {source_repo} version {release_tag}.\n"
                    f"Release URL: {release_url}\n"
                    f"Published at: {published_at}\n\n"
                    "PRs with the release-notes label:\n"
                    f"{pr_summaries}\n\n"
                    "Generate a markdown section with this structure:\n"
                    f"## {release_tag} ({published_at[:10]})\n\n"
                    f"See what's new and improved in version {release_tag}.\n\n"
                    f'<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/{image_number}.jpg" '
                    f'align="left" alt="ZenML {release_tag}" width="800">\n\n'
                    "Use bolded subsection headers (####) to group related changes. "
                    "Use <details><summary>Fixed</summary>...</details> for bug fixes and "
                    "<details><summary>Improved</summary>...</details> for minor improvements when appropriate. "
                    f"{include_links_instruction} "
                    "Highlight the top user-facing improvements first. End the section with *** on its own line."
                ),
            }
        ],
    )
    return response.parsed_output.content


def map_labels(pr_labels: List[str], suggested: List[ChangelogLabel]) -> List[str]:
    mapped = []
    for label in pr_labels:
        mapped_label = LABEL_MAPPING.get(label.lower())
        if mapped_label:
            mapped.append(mapped_label)
    if not mapped and suggested:
        mapped = [label.value for label in suggested]
    if not mapped:
        mapped = ["improvement"]
    return sorted(set(mapped))


def create_changelog_entry(pr: Dict[str, Any], source_repo: str, published_at: str, next_id: int) -> Dict[str, Any]:
    config = REPO_CONFIG[source_repo]
    changelog_copy = llm_generate_changelog_copy(
        pr_title=pr["title"],
        pr_body=pr["body"],
        pr_url=pr["url"],
        repo_type=config["type"],
    )
    labels = map_labels(pr["labels"], changelog_copy.suggested_labels)
    return {
        "id": next_id,
        "slug": slugify_title(pr["title"]),
        "title": changelog_copy.title,
        "description": changelog_copy.description,
        "published_at": published_at,
        "published": True,
        "audience": config["audience"],
        "labels": labels,
    }


def update_markdown_file(md_path: Path, new_section: str) -> None:
    content = md_path.read_text()
    frontmatter = ""
    body = content
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            end += len("\n---")
            frontmatter = content[:end].rstrip("\n")
            body = content[end:].lstrip("\n")
    insertion = new_section.strip() + "\n\n"
    if "## " in body:
        idx = body.index("## ")
        updated_body = body[:idx] + insertion + body[idx:]
    else:
        updated_body = insertion + body
    updated_content = f"{frontmatter}\n\n{updated_body}".lstrip("\n") if frontmatter else updated_body
    md_path.write_text(updated_content.rstrip() + "\n")


def validate_changelog(changelog_path: Path, schema_path: Path) -> None:
    changelog_data = json.loads(changelog_path.read_text())
    schema = json.loads(schema_path.read_text())
    jsonschema_validate(instance=changelog_data, schema=schema)
    print(f"Validated changelog.json with {len(changelog_data)} entries.")


def ensure_required_env(vars_list: List[str]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    missing = []
    for var in vars_list:
        value = os.environ.get(var)
        if value is None:
            missing.append(var)
        else:
            values[var] = value
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    return values


def main() -> None:
    env = ensure_required_env(
        ["SOURCE_REPO", "RELEASE_TAG", "RELEASE_URL", "PUBLISHED_AT", "GITHUB_TOKEN", "ANTHROPIC_API_KEY"]
    )
    source_repo = env["SOURCE_REPO"]
    if source_repo not in REPO_CONFIG:
        raise RuntimeError(f"Repository {source_repo} is not configured for changelog updates")
    github_token = os.environ.get("PRIVATE_REPO_TOKEN") or env["GITHUB_TOKEN"]
    global anthropic_client
    anthropic_client = Anthropic(api_key=env["ANTHROPIC_API_KEY"])
    gh = Github(github_token)

    previous_tag = find_previous_tag(gh, source_repo, env["RELEASE_TAG"])
    print(f"Processing {source_repo} {env['RELEASE_TAG']} (previous: {previous_tag or 'first release'})")
    prs = get_release_prs(gh, source_repo, previous_tag, env["RELEASE_TAG"])
    print(f"Found {len(prs)} PRs with release-notes label")
    if not prs:
        print("No release-notes PRs found; exiting without changes.")
        return

    changelog_path = Path("changelog.json")
    existing_changelog = json.loads(changelog_path.read_text())
    max_existing_id = max((entry.get("id", 0) for entry in existing_changelog), default=0)
    pr_with_ids = [(pr, max_existing_id + idx + 1) for idx, pr in enumerate(prs)]

    new_entries: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(4, len(pr_with_ids))) as executor:
        future_map = {
            executor.submit(create_changelog_entry, pr, source_repo, env["PUBLISHED_AT"], next_id): pr
            for pr, next_id in pr_with_ids
        }
        for future in as_completed(future_map):
            entry = future.result()
            new_entries.append(entry)
            print(f"Created changelog entry #{entry['id']}: {entry['title']}")

    new_entries.sort(key=lambda entry: entry["id"], reverse=True)
    updated_changelog = new_entries + existing_changelog
    changelog_path.write_text(json.dumps(updated_changelog, indent=2) + "\n")
    validate_changelog(changelog_path, Path("changelog_schema/announcement-schema.json"))

    image_number = get_next_image_number()
    md_section = llm_generate_markdown_section(
        prs=prs,
        release_tag=env["RELEASE_TAG"],
        release_url=env["RELEASE_URL"],
        published_at=env["PUBLISHED_AT"],
        repo_type=REPO_CONFIG[source_repo]["type"],
        source_repo=source_repo,
        image_number=image_number,
    )
    update_markdown_file(Path(REPO_CONFIG[source_repo]["markdown_file"]), md_section)
    print(
        f"Updated changelog.json (+{len(new_entries)} entries) and "
        f"{REPO_CONFIG[source_repo]['markdown_file']} (image {image_number})."
    )


if __name__ == "__main__":
    main()
