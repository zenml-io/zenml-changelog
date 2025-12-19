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
import re
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
        "audience": "oss",
        "include_release_link": True,
        "include_compatibility_note": False,
        "sources": [
            {
                "repo": "zenml-io/zenml",
                "default_branch": "develop",
                "github_tag_prefix": "",
            },
            {
                "repo": "zenml-io/zenml-dashboard",
                "default_branch": "staging",
                "github_tag_prefix": "v",
            },
        ],
    },
    "zenml-io/zenml-pro-api": {
        "type": "pro",
        "markdown_file": "gitbook-release-notes/pro-control-plane.md",
        "audience": "pro",
        "include_release_link": False,
        "include_compatibility_note": True,
        "sources": [
            {
                "repo": "zenml-io/zenml-pro-api",
                "default_branch": "develop",
                "github_tag_prefix": "",
            },
            {
                "repo": "zenml-io/zenml-cloud-ui",
                "default_branch": "staging",
                "github_tag_prefix": "",
            },
        ],
    },
}

def get_source_config(repo_name: str) -> Dict[str, Any]:
    for trigger_config in REPO_CONFIG.values():
        for source in trigger_config.get("sources", []):
            if source.get("repo") == repo_name:
                return source
    return {}

def with_prefix(repo_name: str, tag: str) -> str:
    config = get_source_config(repo_name)
    prefix = config.get("github_tag_prefix", "")
    if prefix and tag.startswith(prefix):
        return tag
    return f"{prefix}{tag}"

def strip_prefix(repo_name: str, tag: str) -> str:
    config = get_source_config(repo_name)
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
    "breaking-change": "deprecation",
    "breaking changes": "deprecation",
}

BREAKING_CHANGE_LABELS: List[str] = [
    "breaking-change",
    "breaking changes",
    "breaking",
]

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

class BreakingChangesOutput(BaseModel):
    bullets: List[str] = Field(
        default_factory=list,
        description="List of breaking change bullet points, one per significant breaking change.",
    )

class ImageState(BaseModel):
    last_image_number: int = Field(default=0, ge=0, le=MAX_IMAGE_NUMBER)
    last_release_tag: Optional[str] = None
    last_markdown_file: Optional[str] = None
    updated_at: Optional[str] = None

class MarkdownSection(BaseModel):
    content: str = Field(..., description="Complete markdown section for the release notes")


anthropic_client: Optional[Anthropic] = None

def read_image_state(path: Path = IMAGE_STATE_FILE) -> ImageState:
    if not path.exists():
        return ImageState()

    raw = path.read_text().strip()
    if not raw:
        return ImageState()

    # We support both a legacy integer file and a JSON object so older runs don't break
    # and we can gradually roll out richer metadata without manual intervention.
    try:
        loaded = json.loads(raw)
        if isinstance(loaded, int):
            return ImageState(last_image_number=loaded)
        if isinstance(loaded, dict):
            if hasattr(ImageState, "model_validate"):
                return ImageState.model_validate(loaded)
            return ImageState.parse_obj(loaded)  # type: ignore[attr-defined]
    except json.JSONDecodeError:
        pass
    except Exception:
        return ImageState()

    try:
        return ImageState(last_image_number=int(raw))
    except ValueError:
        return ImageState()

def write_image_state(state: ImageState, path: Path = IMAGE_STATE_FILE) -> None:
    payload = state.model_dump() if hasattr(state, "model_dump") else state.dict()  # type: ignore[attr-defined]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

def infer_latest_image_from_markdown(md_path: Path) -> Optional[int]:
    try:
        text = md_path.read_text()
    except FileNotFoundError:
        return None

    match = re.search(r"projects/(\d+)\.jpg", text)
    if not match:
        return None

    number = int(match.group(1))
    if 0 <= number <= MAX_IMAGE_NUMBER:
        return number
    return None

def infer_latest_release_tag_from_markdown(md_path: Path) -> Optional[str]:
    try:
        text = md_path.read_text()
    except FileNotFoundError:
        return None

    match = re.search(r"^##\s+(\d+\.\d+\.\d+)\b", text, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(1)

def compare_semver_tags(a: str, b: str) -> Optional[int]:
    a_parsed = parse_semver(a)
    b_parsed = parse_semver(b)
    if not a_parsed or not b_parsed:
        return None
    if a_parsed < b_parsed:
        return -1
    if a_parsed > b_parsed:
        return 1
    return 0



def get_next_image_number(release_tag: str, markdown_file: str) -> int:
    state = read_image_state()

    md_path = Path(markdown_file)
    inferred_tag = infer_latest_release_tag_from_markdown(md_path)
    inferred_img = infer_latest_image_from_markdown(md_path)

    # If the markdown already contains a newer release than our state, it means the state
    # file is stale (e.g., merge order across PRs). In that case, we snap to the markdown
    # reality so we don't re-use or regress image numbers.
    if inferred_tag and inferred_img is not None:
        should_snap = False
        if state.last_release_tag:
            cmp = compare_semver_tags(inferred_tag, state.last_release_tag)
            should_snap = cmp == 1
        else:
            should_snap = True

        if should_snap:
            state = ImageState(
                last_image_number=inferred_img,
                last_release_tag=inferred_tag,
                last_markdown_file=markdown_file,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )

    # Idempotency: if we're re-running for the same release and target markdown file,
    # return the existing image number without advancing.
    if state.last_release_tag == release_tag and state.last_markdown_file == markdown_file:
        return state.last_image_number

    next_num = (state.last_image_number % MAX_IMAGE_NUMBER) + 1
    new_state = ImageState(
        last_image_number=next_num,
        last_release_tag=release_tag,
        last_markdown_file=markdown_file,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    write_image_state(new_state)
    return next_num


def find_latest_release_tag(gh: Github, repo_name: str) -> Optional[str]:
    """Find the most recent release tag for a repo."""
    repo = gh.get_repo(repo_name)
    releases = list(repo.get_releases())
    if not releases:
        return None
    releases_sorted = sorted(
        releases,
        key=lambda r: (r.published_at or r.created_at or datetime.min.replace(tzinfo=timezone.utc)),
        reverse=True,
    )
    latest_prefixed = releases_sorted[0].tag_name
    return strip_prefix(repo_name, latest_prefixed)


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

def get_release_window(
    gh: Github,
    repo_name: str,
    since_tag: Optional[str],
    until_tag: str,
) -> Tuple[datetime, datetime]:
    """Compute the date range between two release tags.

    Returns (since_date, until_date) where since_date defaults to 2020-01-01 if no previous tag.
    """
    repo = gh.get_repo(repo_name)
    prefixed_until_tag = with_prefix(repo_name, until_tag)
    until_date = _release_date(repo, prefixed_until_tag)

    if since_tag is None:
        since_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
    else:
        prefixed_since_tag = with_prefix(repo_name, since_tag)
        since_date = _release_date(repo, prefixed_since_tag)

    return since_date, until_date

def search_merged_prs(
    gh: Github,
    repo_name: str,
    base_branch: str,
    since_date: datetime,
    until_date: datetime,
    label: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search for merged PRs in a date range, optionally filtered by label."""
    repo = gh.get_repo(repo_name)

    since_utc = since_date.astimezone(timezone.utc) if since_date.tzinfo else since_date.replace(tzinfo=timezone.utc)
    until_utc = until_date.astimezone(timezone.utc) if until_date.tzinfo else until_date.replace(tzinfo=timezone.utc)

    since_str = since_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    until_str = until_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    query = f"repo:{repo_name} is:pr is:merged base:{base_branch} merged:{since_str}..{until_str}"
    if label:
        query = f'{query} label:"{label}"'

    search_results = gh.search_issues(query)
    prs: List[Dict[str, Any]] = []
    for issue in search_results:
        pr = repo.get_pull(issue.number)
        if not pr.merged_at:
            continue

        merged_at = pr.merged_at
        if merged_at.tzinfo is None:
            merged_at = merged_at.replace(tzinfo=timezone.utc)

        prs.append(
            {
                "number": pr.number,
                "title": pr.title,
                "url": pr.html_url,
                "author": pr.user.login if pr.user else "unknown",
                "body": pr.body or "",
                "labels": [label_item.name for label_item in pr.labels],
                "merged_at": merged_at,
                "repo": repo_name,
            }
        )

    prs.sort(key=lambda pr_item: pr_item["merged_at"])
    return prs

def dedupe_prs_by_number(prs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate PRs by number, keeping first occurrence, then sort by merged_at."""
    seen: set[Tuple[str, int]] = set()
    unique: List[Dict[str, Any]] = []
    for pr in prs:
        repo_name = pr.get("repo", "")
        number = int(pr["number"])
        key = (repo_name, number)
        if key in seen:
            continue
        seen.add(key)
        unique.append(pr)

    def merged_at_key(pr_item: Dict[str, Any]) -> datetime:
        merged_at = pr_item.get("merged_at")
        if not isinstance(merged_at, datetime):
            return datetime.min.replace(tzinfo=timezone.utc)
        if merged_at.tzinfo is None:
            return merged_at.replace(tzinfo=timezone.utc)
        return merged_at

    unique.sort(key=merged_at_key)
    return unique


def parse_semver(tag: str) -> Optional[Tuple[int, int, int]]:
    """Parse a semver tag like '0.91.0' or '1.0.0' into (major, minor, patch).

    Returns None if the tag doesn't match semver pattern.
    Handles tags with or without 'v' prefix.
    """
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", (tag or "").strip())
    if not match:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch

def is_major_bump(previous_tag: Optional[str], current_tag: str) -> bool:
    """Check if the version change represents a major version bump.

    Returns True only if current_major > previous_major.
    Returns False if either tag can't be parsed or if previous_tag is None.
    """
    if previous_tag is None:
        return False
    previous = parse_semver(previous_tag)
    current = parse_semver(current_tag)
    if not previous or not current:
        return False
    return current[0] > previous[0]

def get_multi_source_release_prs(
    gh: Github,
    trigger_repo: str,
    trigger_release_tag: str,
) -> List[Dict[str, Any]]:
    """Collect release-notes PRs for a trigger repo across its configured sources."""
    config = REPO_CONFIG.get(trigger_repo)
    if config is None:
        raise RuntimeError(f"Repository {trigger_repo} is not configured for changelog updates")

    sources = config.get("sources", [])
    if not sources:
        return []

    # Primary source is the trigger repo itself (first in list)
    primary_source = sources[0]["repo"]

    all_prs: List[Dict[str, Any]] = []
    for source in sources:
        source_repo = source["repo"]

        if source_repo == primary_source:
            # Trigger repo: use the provided trigger_release_tag
            current_tag = trigger_release_tag
        else:
            # Bundled repo: find its latest release (guaranteed to exist per team agreements)
            current_tag = find_latest_release_tag(gh, source_repo)
            if current_tag is None:
                print(f"Warning: No releases found for bundled repo {source_repo}, skipping")
                continue

        previous_tag = find_previous_tag(gh, source_repo, current_tag)
        since_date, until_date = get_release_window(
            gh=gh,
            repo_name=source_repo,
            since_tag=previous_tag,
            until_tag=current_tag,
        )
        source_prs = search_merged_prs(
            gh=gh,
            repo_name=source_repo,
            base_branch=source.get("default_branch", "main"),
            since_date=since_date,
            until_date=until_date,
            label="release-notes",
        )
        print(f"  {source_repo}: {len(source_prs)} PRs ({previous_tag or 'start'} → {current_tag})")
        all_prs.extend(source_prs)

    return dedupe_prs_by_number(all_prs)


def get_multi_source_breaking_prs(
    gh: Github,
    trigger_repo: str,
    trigger_release_tag: str,
) -> List[Dict[str, Any]]:
    """Collect breaking-change PRs for a trigger repo across its configured sources."""
    config = REPO_CONFIG.get(trigger_repo)
    if config is None:
        raise RuntimeError(f"Repository {trigger_repo} is not configured for changelog updates")

    sources = config.get("sources", [])
    if not sources:
        return []

    # Primary source is the trigger repo itself (first in list)
    primary_source = sources[0]["repo"]

    all_prs: List[Dict[str, Any]] = []
    for source in sources:
        source_repo = source["repo"]

        if source_repo == primary_source:
            # Trigger repo: use the provided trigger_release_tag
            current_tag = trigger_release_tag
        else:
            # Bundled repo: find its latest release (guaranteed to exist per team agreements)
            current_tag = find_latest_release_tag(gh, source_repo)
            if current_tag is None:
                print(f"Warning: No releases found for bundled repo {source_repo}, skipping")
                continue

        previous_tag = find_previous_tag(gh, source_repo, current_tag)
        since_date, until_date = get_release_window(
            gh=gh,
            repo_name=source_repo,
            since_tag=previous_tag,
            until_tag=current_tag,
        )
        for breaking_label in BREAKING_CHANGE_LABELS:
            source_prs = search_merged_prs(
                gh=gh,
                repo_name=source_repo,
                base_branch=source.get("default_branch", "main"),
                since_date=since_date,
                until_date=until_date,
                label=breaking_label,
            )
            all_prs.extend(source_prs)

    return dedupe_prs_by_number(all_prs)


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
def llm_generate_breaking_changes_bullets(
    breaking_prs: List[Dict[str, Any]],
    source_repo: str,
    include_pr_links: bool,
) -> List[str]:
    """Generate user-facing bullet points summarizing breaking changes from PRs."""
    if not breaking_prs:
        return []

    if anthropic_client is None:
        raise RuntimeError("Anthropic client not initialized")

    config = REPO_CONFIG[source_repo]
    repo_type = config["type"]
    audience = "open source users" if repo_type == "oss" else "ZenML Pro users"

    pr_summaries = "\n".join(
        (
            f"- #{pr['number']}: {pr['title']}\n"
            f"  Labels: {', '.join(pr.get('labels', [])) or 'none'}\n"
            f"  URL: {pr['url']}\n"
            f"  Body (truncated): {(pr.get('body') or '')[:700].replace(chr(10), ' ')}"
        )
        for pr in breaking_prs
    )

    link_instruction = (
        "Include a markdown link to the PR in each bullet using the exact format "
        "[PR #<number>](<url>). If you combine closely related breaking PRs into one bullet, "
        "include all relevant PR links in that bullet."
        if include_pr_links
        else "Do not include PR links, URLs, or PR numbers in the bullets; keep the prose concise."
    )

    response = anthropic_client.beta.messages.parse(
        model="claude-sonnet-4-5-20250929",
        betas=["structured-outputs-2025-11-13"],
        max_tokens=900,
        temperature=0,
        output_format=BreakingChangesOutput,
        messages=[
            {
                "role": "user",
                "content": (
                    "You are writing the \"Breaking Changes\" section for ZenML release notes.\n\n"
                    f"Repository: {source_repo}\n"
                    f"Audience: {audience}\n\n"
                    "Here are PRs labeled as breaking changes for this release:\n\n"
                    f"{pr_summaries}\n\n"
                    "Task:\n"
                    "- Write user-facing bullet point text summarizing what is breaking and how users should adapt.\n"
                    "- Produce one bullet per breaking PR, unless a small grouping is clearly warranted.\n"
                    f"- {link_instruction}\n"
                    "- Each bullet must be plain text only and must NOT start with '-' or '*'. "
                    "The caller will format bullets.\n"
                    "- Avoid implementation details; focus on behavioral changes, removals, renamed APIs, "
                    "compatibility requirements, or required migration steps.\n"
                    "- If there is nothing meaningful to summarize, return an empty list.\n"
                ),
            }
        ],
    )
    return response.parsed_output.bullets

def render_release_header(
    release_tag: str,
    published_at: str,
    image_number: int,
    source_repo: str,
) -> str:
    """Render the deterministic header portion of release notes."""
    config = REPO_CONFIG[source_repo]
    repo_type = config["type"]
    alt_prefix = "ZenML Pro" if repo_type == "pro" else "ZenML"

    return (
        f"## {release_tag} ({published_at[:10]})\n\n"
        f"See what's new and improved in version {release_tag}.\n\n"
        f'<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/{image_number}.jpg" '
        f'align="left" alt="{alt_prefix} {release_tag}" width="800">\n\n'
    )

def render_breaking_section(
    bullets: List[str],
    force_placeholder: bool,
    is_major_bump: bool,
) -> str:
    """Render the Breaking Changes section.

    Returns empty string if no bullets and not forced.
    If forced (major bump) but no bullets, returns placeholder text.
    """
    bullets_clean = [bullet.strip() for bullet in (bullets or []) if bullet and bullet.strip()]
    if bullets_clean:
        formatted = "\n".join(f"* {bullet}" for bullet in bullets_clean)
        return f"### Breaking Changes\n\n{formatted}\n\n"

    forced = force_placeholder or is_major_bump
    if not forced:
        return ""

    placeholder = (
        "* This is a major release. No PRs were labeled as breaking changes; "
        "please review manually for any breaking changes."
    )
    return f"### Breaking Changes\n\n{placeholder}\n\n"

def render_release_footer(source_repo: str, release_url: str) -> str:
    """Render the deterministic footer portion of release notes."""
    config = REPO_CONFIG[source_repo]

    footer_parts: List[str] = []
    if config.get("include_release_link"):
        footer_parts.append(f"[View full release on GitHub]({release_url})")
    if config.get("include_compatibility_note"):
        footer_parts.append("> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.")

    if footer_parts:
        return "\n\n".join(footer_parts) + "\n\n***"
    return "***"

@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    retry=retry_if_exception_type((APIError, RateLimitError)),
)
def llm_generate_release_notes_body(
    prs: List[Dict[str, Any]],
    source_repo: str,
    include_pr_links: bool,
) -> str:
    """Generate the body portion of release notes (no header, footer, or breaking section)."""
    if not prs:
        return ""

    if anthropic_client is None:
        raise RuntimeError("Anthropic client not initialized")

    config = REPO_CONFIG[source_repo]
    repo_type = config["type"]
    audience = "open source users" if repo_type == "oss" else "ZenML Pro users"

    pr_summaries = "\n".join(
        f"- {pr['title']} (#{pr['number']}): {pr['url']} — {(pr.get('body') or '')[:500].replace(chr(10), ' ')}"
        for pr in prs
    )

    include_links_instruction = (
        "Include a markdown link to each PR using the format [PR #<number>](<url>) where relevant."
        if include_pr_links
        else "Do not include PR links, URLs, or PR numbers; keep the prose concise."
    )

    response = anthropic_client.beta.messages.parse(
        model="claude-sonnet-4-5-20250929",
        betas=["structured-outputs-2025-11-13"],
        max_tokens=1800,
        temperature=0,
        output_format=MarkdownSection,
        messages=[
            {
                "role": "user",
                "content": (
                    "You are writing the release notes body for ZenML.\n\n"
                    f"Repository: {source_repo}\n"
                    f"Audience: {audience}\n\n"
                    "Merged PRs to cover (release-notes label):\n"
                    f"{pr_summaries}\n\n"
                    "Output rules (CRITICAL):\n"
                    "- Output markdown for the body only.\n"
                    "- Do NOT include the `## <release_tag>` header (the caller will render the release header).\n"
                    "- Do NOT include the `<img>` tag.\n"
                    "- Do NOT include a \"Breaking Changes\" heading.\n"
                    "- Do NOT include the footer, any release link section, or `***`.\n\n"
                    "Formatting requirements:\n"
                    "- Use `####` subsection headers to group related changes by theme.\n"
                    "- Use `<details><summary>Fixed</summary>...</details>` for bug fixes.\n"
                    f"- {include_links_instruction}\n\n"
                    "Writing guidance:\n"
                    "- Highlight the most user-facing improvements first.\n"
                    "- Avoid low-level implementation details; focus on what users can now do.\n"
                    "- Keep it readable and scannable.\n"
                ),
            }
        ],
    )
    return response.parsed_output.content

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

    config = REPO_CONFIG[source_repo]
    primary_source = config["sources"][0]["repo"]
    primary_previous_tag = find_previous_tag(gh, primary_source, env["RELEASE_TAG"])
    print(
        f"Processing {source_repo} {env['RELEASE_TAG']} "
        f"(primary previous: {primary_previous_tag or 'first release'})"
    )

    release_notes_prs = get_multi_source_release_prs(gh, source_repo, env["RELEASE_TAG"])
    print(f"Found {len(release_notes_prs)} PRs with release-notes label across all sources")

    breaking_prs = get_multi_source_breaking_prs(gh, source_repo, env["RELEASE_TAG"])
    print(f"Found {len(breaking_prs)} PRs with breaking-change labels across all sources")

    major_bump = is_major_bump(primary_previous_tag, env["RELEASE_TAG"])
    if major_bump:
        print("Detected major version bump - will force Breaking Changes section")

    if not release_notes_prs and not breaking_prs:
        print("ERROR: No release-notes or breaking-change PRs found for this release.")
        raise SystemExit(1)

    # Use release-notes PRs for changelog entries; fall back to breaking PRs if none
    grouping_prs = release_notes_prs if release_notes_prs else breaking_prs

    breaking_pr_keys = {(pr.get("repo", ""), pr["number"]) for pr in breaking_prs}
    body_prs = [pr for pr in release_notes_prs if (pr.get("repo", ""), pr["number"]) not in breaking_pr_keys]

    include_pr_links = config["type"] == "oss"
    breaking_bullets = llm_generate_breaking_changes_bullets(
        breaking_prs=breaking_prs,
        source_repo=source_repo,
        include_pr_links=include_pr_links,
    )

    changelog_path = Path("changelog.json")
    existing_changelog = json.loads(changelog_path.read_text())
    max_existing_id = max((entry.get("id", 0) for entry in existing_changelog), default=0)
    starting_id = max_existing_id + 1

    # Identify PRs with insufficient descriptions that should be reviewed manually
    needs_attention = collect_needs_attention(grouping_prs)
    if not release_notes_prs and breaking_prs:
        needs_attention.append(
            {
                "number": "N/A",
                "title": "No release-notes PRs found; changelog derived from breaking PRs only",
                "url": "",
            }
        )

    # Use a single LLM call to create 2-3 grouped, thematic changelog entries
    grouped_output = llm_generate_grouped_changelog_entries(
        prs=grouping_prs,
        source_repo=source_repo,
    )
    new_entries = build_grouped_changelog_entries(
        grouped_output=grouped_output,
        prs=grouping_prs,
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

    markdown_file = config["markdown_file"]
    image_number = get_next_image_number(
        release_tag=env["RELEASE_TAG"],
        markdown_file=markdown_file,
    )
    header = render_release_header(env["RELEASE_TAG"], published_at, image_number, source_repo)
    breaking_section = render_breaking_section(
        breaking_bullets, force_placeholder=False, is_major_bump=major_bump
    )
    body = llm_generate_release_notes_body(body_prs, source_repo, include_pr_links) if body_prs else ""
    footer = render_release_footer(source_repo, release_url)
    md_section = header + breaking_section + body + "\n\n" + footer

    update_markdown_file(Path(markdown_file), md_section)
    print(
        f"Updated changelog.json (+{len(new_entries)} entries) and "
        f"{config['markdown_file']} (image {image_number})."
    )

    if breaking_section.strip():
        print()
        print("BREAKING_CHANGES")
        # Print just the bullets portion for extraction
        for bullet in breaking_bullets:
            print(f"- {bullet}")
        if major_bump and not breaking_bullets:
            print("- Major version bump detected; manual review recommended")
        print("END_BREAKING_CHANGES")

    if needs_attention:
        print()
        print("NEEDS_ATTENTION")
        print("The following PRs had empty or insufficient descriptions and need manual review:")
        for pr in needs_attention:
            print(f"- PR #{pr['number']}: {pr['title']} ({pr['url']})")

    print()
    print("UPDATED_MARKDOWN_FILE")
    print(config["markdown_file"])
    print("END_UPDATED_MARKDOWN_FILE")

if __name__ == "__main__":
    main()
