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
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from anthropic import Anthropic, APIError, RateLimitError
from github import Auth, Github
from jsonschema import validate as jsonschema_validate
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from pydantic import BaseModel, Field
from slugify import slugify
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

IMAGE_STATE_FILE = Path(".image_state")
MAX_IMAGE_NUMBER = 49

REPO_CONFIG: Dict[str, Dict[str, Any]] = {
    "zenml-io/zenml": {
        "type": "oss",
        "markdown_file": "gitbook-release-notes/server-sdk.md",
        "default_branch": "develop",
        "audience": "oss",
        "include_release_link": True,
        "include_compatibility_note": False,
        "github_tag_prefix": "",
    },
    "zenml-io/zenml-dashboard": {
        "type": "oss",
        "markdown_file": "gitbook-release-notes/server-sdk.md",
        "default_branch": "staging",
        "audience": "oss",
        "include_release_link": False,
        "include_compatibility_note": False,
        "github_tag_prefix": "v",
    },
    "zenml-io/zenml-cloud-ui": {
        "type": "pro",
        "markdown_file": "gitbook-release-notes/pro-control-plane.md",
        "default_branch": "staging",
        "audience": "pro",
        "include_release_link": False,
        "include_compatibility_note": False,
        "github_tag_prefix": "",
    },
    "zenml-io/zenml-cloud-api": {
        "type": "pro",
        "markdown_file": "gitbook-release-notes/pro-control-plane.md",
        "default_branch": "develop",
        "audience": "pro",
        "include_release_link": False,
        "include_compatibility_note": True,
        "github_tag_prefix": "",
    },
}

def with_prefix(repo_name: str, tag: str) -> str:
    config = REPO_CONFIG.get(repo_name, {})
    return f"{config.get('github_tag_prefix', '')}{tag}"

def strip_prefix(repo_name: str, tag: str) -> str:
    config = REPO_CONFIG.get(repo_name, {})
    prefix = config.get("github_tag_prefix", "")
    if prefix and tag.startswith(prefix):
        return tag[len(prefix) :]
    return tag

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

# Placeholder URLs that pass schema validation but are clearly marked for review
PLACEHOLDER_LEARN_MORE_URL = "https://example.com/REPLACE-ME"
PLACEHOLDER_DOCS_URL = "https://docs.zenml.io/REPLACE-ME"


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

class GroupedChangelogEntry(BaseModel):
    title: str = Field(
        ...,
        max_length=60,
        description="User-facing title for a group of related PRs, no PR numbers.",
    )
    description: str = Field(
        ...,
        description="1-3 sentences summarizing the grouped theme in user terms, markdown allowed.",
    )
    suggested_labels: List[ChangelogLabel] = Field(
        default_factory=list,
        description="Suggested labels based on all PRs in this group.",
    )
    pr_numbers: List[int] = Field(
        ...,
        min_length=1,
        description="List of PR numbers covered by this group.",
    )

class GroupedChangelogOutput(BaseModel):
    entries: List[GroupedChangelogEntry] = Field(
        ...,
        min_length=1,
        max_length=3,
        description="2-3 grouped changelog entries summarizing the release.",
    )

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
    prefixed_current_tag = with_prefix(repo_name, current_tag)
    releases_sorted = sorted(
        releases,
        key=lambda r: (r.published_at or r.created_at or datetime.min.replace(tzinfo=timezone.utc)),
    )
    tag_index = next((i for i, rel in enumerate(releases_sorted) if rel.tag_name == prefixed_current_tag), None)
    if tag_index is None:
        raise RuntimeError(f"Release tag {prefixed_current_tag} not found in {repo_name}")
    if tag_index == 0:
        return None
    previous_prefixed = releases_sorted[tag_index - 1].tag_name
    return strip_prefix(repo_name, previous_prefixed)


def _release_date(repo, prefixed_tag: str) -> datetime:
    """Return release timestamp for a tag that already includes any repo-specific prefix."""
    release = repo.get_release(prefixed_tag)
    published = release.published_at or release.created_at
    if not published:
        raise RuntimeError(f"Release {prefixed_tag} in {repo.full_name} has no published/created date")
    if not published.tzinfo:
        published = published.replace(tzinfo=timezone.utc)
    return published


def get_release_prs(gh: Github, repo_name: str, since_tag: Optional[str], until_tag: str) -> List[Dict[str, Any]]:
    repo = gh.get_repo(repo_name)
    config = REPO_CONFIG[repo_name]
    prefixed_until_tag = with_prefix(repo_name, until_tag)
    prefixed_since_tag = with_prefix(repo_name, since_tag) if since_tag else None
    until_date = _release_date(repo, prefixed_until_tag)
    since_date = _release_date(repo, prefixed_since_tag) if prefixed_since_tag else datetime(2020, 1, 1, tzinfo=timezone.utc)
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
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    retry=retry_if_exception_type((APIError, RateLimitError)),
)
def llm_generate_changelog_copy(pr_title: str, pr_body: str, pr_url: str, repo_type: str) -> ChangelogCopy:
    # NOTE: This helper is primarily intended for ad-hoc or manual usage.
    # The main automation flow uses llm_generate_grouped_changelog_entries to create grouped entries per release.
    if anthropic_client is None:
        raise RuntimeError("Anthropic client not initialized")
    audience = "open source users" if repo_type == "oss" else "ZenML Pro users"
    response = anthropic_client.beta.messages.parse(
        model="claude-sonnet-4-5-20250929",
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
                    "description, and suggest appropriate labels. "
                    "Feel free to include inline markdown links to well-known tools and libraries (e.g., "
                    "[MLflow](https://github.com/mlflow/mlflow), [Transformers](https://github.com/huggingface/transformers)). "
                    "Prefer linking to GitHub repos when available."
                ),
            }
        ],
    )
    return response.parsed_output

@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    retry=retry_if_exception_type((APIError, RateLimitError)),
)
def llm_generate_grouped_changelog_entries(
    prs: List[Dict[str, Any]],
    source_repo: str,
) -> GroupedChangelogOutput:
    if anthropic_client is None:
        raise RuntimeError("Anthropic client not initialized")

    config = REPO_CONFIG[source_repo]
    repo_type = config["type"]
    audience = "open source users" if repo_type == "oss" else "ZenML Pro users"

    if not prs:
        raise RuntimeError("No PRs provided to llm_generate_grouped_changelog_entries")

    pr_summaries = "\n".join(
        (
            f"- #{pr['number']}: {pr['title']}\n"
            f"  Labels: {', '.join(pr['labels']) or 'none'}\n"
            f"  URL: {pr['url']}\n"
            f"  Body (truncated): {(pr['body'] or '')[:400].replace(chr(10), ' ')}"
        )
        for pr in prs
    )

    response = anthropic_client.beta.messages.parse(
        model="claude-sonnet-4-5-20250929",
        betas=["structured-outputs-2025-11-13"],
        max_tokens=1200,
        temperature=0,
        output_format=GroupedChangelogOutput,
        messages=[
            {
                "role": "user",
                "content": (
                    "You are helping write grouped changelog entries for ZenML, an MLOps platform.\n\n"
                    "Here is the list of merged PRs with the `release-notes` label for this release. "
                    "Each PR includes its number, title, labels, URL, and a truncated body:\n\n"
                    f"{pr_summaries}\n\n"
                    f"The audience is {audience}. Focus on what users can now do or benefit from.\n\n"
                    "Your task:\n"
                    "- Group these PRs into 2-3 thematic user-facing changelog entries when possible. "
                    "For very small releases, 1 entry is acceptable.\n"
                    "- Each entry should summarize a coherent theme or area of improvement.\n"
                    "- Every PR must appear in exactly one group.\n"
                    "- Do not include PR numbers in the titles or descriptions.\n"
                    "- Use markdown-friendly prose in the descriptions (1-3 sentences).\n\n"
                    "Output format rules:\n"
                    "- Produce between 1 and 3 entries in total (2-3 preferred when the number of PRs allows it).\n"
                    "- For each entry, set `title`, `description`, `suggested_labels`, and `pr_numbers`.\n"
                    "- `pr_numbers` must be a list of the PR numbers from the list above that this entry covers.\n"
                    "- Use `suggested_labels` based on the overall theme of the grouped PRs, using only: "
                    "feature, improvement, bugfix, deprecation.\n"
                    "Avoid low-level implementation details and emphasize user-facing value."
                ),
            }
        ],
    )
    return response.parsed_output

@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    retry=retry_if_exception_type((APIError, RateLimitError)),
)
def llm_generate_markdown_section(
    prs: List[Dict[str, Any]],
    release_tag: str,
    release_url: str,
    published_at: str,
    source_repo: str,
    image_number: int,
) -> str:
    if anthropic_client is None:
        raise RuntimeError("Anthropic client not initialized")
    config = REPO_CONFIG[source_repo]
    repo_type = config["type"]
    pr_summaries = "\n".join(
        f"- {pr['title']} (#{pr['number']}): {pr['url']} — {pr['body'][:300].replace(chr(10), ' ')}"
        for pr in prs
    )
    include_links_instruction = (
        "Include a markdown link to each PR using the format [PR #<number>](<url>) for each bullet."
        if repo_type == "oss"
        else "Do not include PR links; keep the prose concise for Pro audiences."
    )
    footer_parts: List[str] = []
    if config.get("include_release_link"):
        footer_parts.append(f"[View full release on GitHub]({release_url})")
    if config.get("include_compatibility_note"):
        footer_parts.append("> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.")
    if footer_parts:
        footer_instruction = "Append at the end:\n" + "\n\n".join(footer_parts) + "\n\n***"
    else:
        footer_instruction = "End the section with *** on its own line."
    response = anthropic_client.beta.messages.parse(
        model="claude-sonnet-4-5-20250929",
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
                    "Feel free to include inline markdown links to well-known tools and libraries (e.g., "
                    "[MLflow](https://github.com/mlflow/mlflow), [Transformers](https://github.com/huggingface/transformers)). "
                    "Prefer linking to GitHub repos when available. "
                    "Highlight the top user-facing improvements first. "
                    f"{footer_instruction}"
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


def is_short_body(pr_body: str, threshold: int = 50) -> bool:
    return len((pr_body or "").strip()) < threshold

def collect_needs_attention(
    prs: List[Dict[str, Any]],
    threshold: int = 50,
) -> List[Dict[str, str]]:
    """Identify PRs with insufficient bodies that should be highlighted for manual review."""
    needs_attention: List[Dict[str, str]] = []
    for pr in prs:
        if is_short_body(pr.get("body", ""), threshold=threshold):
            needs_attention.append(
                {
                    "number": str(pr["number"]),
                    "title": pr["title"][:60],
                    "url": pr["url"],
                }
            )
    return needs_attention

def build_grouped_changelog_entries(
    grouped_output: GroupedChangelogOutput,
    prs: List[Dict[str, Any]],
    source_repo: str,
    published_at: str,
    starting_id: int,
) -> List[Dict[str, Any]]:
    """Convert grouped LLM output into schema-compliant changelog entries."""
    pr_by_number: Dict[int, Dict[str, Any]] = {pr["number"]: pr for pr in prs}
    all_known_numbers = set(pr_by_number.keys())
    assigned_numbers: set[int] = set()

    for entry in grouped_output.entries:
        for pr_number in entry.pr_numbers:
            if pr_number not in pr_by_number:
                raise RuntimeError(
                    f"Grouped changelog entry references unknown PR number #{pr_number}"
                )
            if pr_number in assigned_numbers:
                raise RuntimeError(
                    f"PR #{pr_number} appears in more than one grouped changelog entry"
                )
            assigned_numbers.add(pr_number)

    unassigned = all_known_numbers - assigned_numbers
    if unassigned:
        missing_str = ", ".join(f"#{n}" for n in sorted(unassigned))
        raise RuntimeError(
            f"The following PRs were not assigned to any grouped changelog entry: {missing_str}"
        )

    config = REPO_CONFIG[source_repo]
    entries: List[Dict[str, Any]] = []
    group_count = len(grouped_output.entries)
    base_id = starting_id - 1

    for index, entry in enumerate(grouped_output.entries):
        aggregate_labels: List[str] = []
        for pr_number in entry.pr_numbers:
            aggregate_labels.extend(pr_by_number[pr_number].get("labels", []))
        labels = map_labels(aggregate_labels, entry.suggested_labels)

        # Assign IDs so that the first group gets the highest ID, preserving LLM order
        # when new entries are later sorted in descending ID order.
        entry_id = base_id + (group_count - index)

        entries.append(
            {
                "id": entry_id,
                "slug": slugify_title(entry.title),
                "title": entry.title,
                "description": entry.description,
                "published_at": published_at,
                "published": True,
                "audience": config["audience"],
                "labels": labels,
                # Optional fields below - replace placeholders as needed
                "feature_image_url": "",
                "video_url": "",
                "learn_more_url": PLACEHOLDER_LEARN_MORE_URL,
                "docs_url": PLACEHOLDER_DOCS_URL,
                "should_highlight": False,
            }
        )

    return entries


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


def get_release_info(gh: Github, repo_name: str, tag: str) -> tuple[str, str]:
    """Fetch release URL and published_at from GitHub API."""
    repo = gh.get_repo(repo_name)
    prefixed_tag = with_prefix(repo_name, tag)
    release = repo.get_release(prefixed_tag)
    published_at = release.published_at or release.created_at
    if published_at:
        published_at_str = published_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        published_at_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return release.html_url, published_at_str


def main() -> None:
    env = ensure_required_env(
        ["SOURCE_REPO", "RELEASE_TAG", "GITHUB_TOKEN", "ANTHROPIC_API_KEY"]
    )
    source_repo = env["SOURCE_REPO"]
    if source_repo not in REPO_CONFIG:
        raise RuntimeError(f"Repository {source_repo} is not configured for changelog updates")
    github_token = os.environ.get("PRIVATE_REPO_TOKEN") or env["GITHUB_TOKEN"]
    global anthropic_client
    anthropic_client = Anthropic(api_key=env["ANTHROPIC_API_KEY"])
    gh = Github(auth=Auth.Token(github_token))

    # Fetch release info from GitHub if not provided (for manual triggers)
    release_url = os.environ.get("RELEASE_URL") or ""
    published_at = os.environ.get("PUBLISHED_AT") or ""
    if not release_url or not published_at:
        print(f"Fetching release info from GitHub for {source_repo}@{env['RELEASE_TAG']}...")
        release_url, published_at = get_release_info(gh, source_repo, env["RELEASE_TAG"])

    previous_tag = find_previous_tag(gh, source_repo, env["RELEASE_TAG"])
    print(f"Processing {source_repo} {env['RELEASE_TAG']} (previous: {previous_tag or 'first release'})")
    prs = get_release_prs(gh, source_repo, previous_tag, env["RELEASE_TAG"])
    print(f"Found {len(prs)} PRs with release-notes label")
    if not prs:
        print("ERROR: No release-notes PRs found for this release.")
        print("This likely means no PRs were labeled with 'release-notes' between the releases.")
        raise SystemExit(1)

    changelog_path = Path("changelog.json")
    existing_changelog = json.loads(changelog_path.read_text())
    max_existing_id = max((entry.get("id", 0) for entry in existing_changelog), default=0)
    starting_id = max_existing_id + 1

    # Identify PRs with insufficient descriptions that should be reviewed manually
    needs_attention = collect_needs_attention(prs)

    # Use a single LLM call to create 2-3 grouped, thematic changelog entries
    grouped_output = llm_generate_grouped_changelog_entries(
        prs=prs,
        source_repo=source_repo,
    )
    new_entries = build_grouped_changelog_entries(
        grouped_output=grouped_output,
        prs=prs,
        source_repo=source_repo,
        published_at=published_at,
        starting_id=starting_id,
    )

    for entry in new_entries:
        print(f"Created grouped changelog entry #{entry['id']}: {entry['title']}")

    new_entries.sort(key=lambda entry: entry["id"], reverse=True)
    updated_changelog = new_entries + existing_changelog
    changelog_path.write_text(json.dumps(updated_changelog, indent=2) + "\n")
    validate_changelog(changelog_path, Path("changelog_schema/announcement-schema.json"))

    image_number = get_next_image_number()
    md_section = llm_generate_markdown_section(
        prs=prs,
        release_tag=env["RELEASE_TAG"],
        release_url=release_url,
        published_at=published_at,
        source_repo=source_repo,
        image_number=image_number,
    )
    update_markdown_file(Path(REPO_CONFIG[source_repo]["markdown_file"]), md_section)
    print(
        f"Updated changelog.json (+{len(new_entries)} entries) and "
        f"{REPO_CONFIG[source_repo]['markdown_file']} (image {image_number})."
    )

    if needs_attention:
        print()
        print("NEEDS_ATTENTION")
        print("The following PRs had empty or insufficient descriptions and need manual review:")
        for pr in needs_attention:
            print(f"- PR #{pr['number']}: {pr['title']} ({pr['url']})")


if __name__ == "__main__":
    main()
