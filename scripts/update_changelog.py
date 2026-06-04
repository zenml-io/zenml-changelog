#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests",
#     "PyGithub",
#     "anthropic",
#     "openai",
#     "jsonschema",
#     "pydantic>=2",
#     "python-slugify",
#     "tenacity",
# ]
# ///
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from github import Auth, Github
from pydantic import BaseModel, Field

try:
    from scripts import changelog_llm_providers as _llm_providers
    from scripts.changelog_artifact_safety import (
        unsafe_relative_artifact_path_reason,
    )
    from scripts.changelog_config import (
        BREAKING_CHANGE_LABELS,
        LABEL_MAPPING,
        PLACEHOLDER_DOCS_URL,
        PLACEHOLDER_LEARN_MORE_URL,
        REPO_CONFIG,
        get_source_config,
        strip_prefix,
        with_prefix,
    )
    from scripts.changelog_entry_builder import (
        build_grouped_changelog_entries,
        map_labels,
        slugify_title,
    )
    from scripts.changelog_env import env_value, require_env_values
    from scripts.changelog_llm_generation import (
        generate_breaking_changes_output,
        generate_grouped_changelog_output,
        generate_release_notes_body_output,
    )
    from scripts.changelog_llm_outputs import (
        LLM_CALL_BREAKING_CHANGES,
        LLM_CALL_CHANGELOG_COPY,
        LLM_CALL_GROUPED_CHANGELOG_ENTRIES,
        LLM_CALL_MARKDOWN_SECTION,
        LLM_CALL_RELEASE_NOTES_BODY,
        Audience,
        BreakingChangesOutput,
        ChangelogCopy,
        ChangelogLabel,
        GroupedChangelogEntry,
        GroupedChangelogOutput,
        MarkdownSection,
    )
    from scripts.changelog_llm_providers import (
        DEFAULT_ANTHROPIC_MODEL,
        DEFAULT_LLM_PROVIDER,
        DEFAULT_OPENAI_MODEL,
        LLM_MODEL_ENV,
        LLM_PROVIDER_ENV,
        LLM_PROVIDER_OPENAI,
        Anthropic,
        AnthropicStructuredLLMClient,
        LLMOutputValidationError,
        LLMProviderNonRetryableError,
        LLMProviderRetryableError,
        OpenAI,
        OpenAIStructuredLLMClient,
        StructuredLLMClient,
        build_openai_structured_llm_client,
        llm_retryable,
        openai_response_has_refusal,
    )
    from scripts.changelog_prompts import (
        build_breaking_changes_prompt,
        build_changelog_copy_prompt,
        build_grouped_changelog_entries_prompt,
        build_markdown_section_prompt,
        build_release_notes_body_prompt,
    )
    from scripts.changelog_rendering import (
        render_breaking_section,
        render_release_footer,
        render_release_header,
        render_release_notes_section,
        update_markdown_file,
    )
    from scripts.changelog_schema_validation import (
        validate_changelog,
        validate_changelog_data,
    )
    from scripts.changelog_validators import (
        GroupedChangelogSemanticError,
        assert_unique_grouped_pr_numbers,
        build_grouped_retry_feedback,
        contains_forbidden_pr_reference,
        format_grouped_attempt_summaries,
        format_repo_qualified_pr,
        markdown_pr_link_pattern,
        missing_markdown_pr_links,
        summarize_grouped_changelog_output,
        validate_breaking_changes_output,
        validate_grouped_changelog_output,
        validate_release_notes_body_output,
    )
except ModuleNotFoundError:  # pragma: no cover - direct `uv run scripts/update_changelog.py`
    import changelog_llm_providers as _llm_providers  # type: ignore[no-redef]
    from changelog_artifact_safety import (  # type: ignore[no-redef]
        unsafe_relative_artifact_path_reason,
    )
    from changelog_config import (  # type: ignore[no-redef]
        BREAKING_CHANGE_LABELS,
        LABEL_MAPPING,
        PLACEHOLDER_DOCS_URL,
        PLACEHOLDER_LEARN_MORE_URL,
        REPO_CONFIG,
        get_source_config,
        strip_prefix,
        with_prefix,
    )
    from changelog_entry_builder import (  # type: ignore[no-redef]
        build_grouped_changelog_entries,
        map_labels,
        slugify_title,
    )
    from changelog_env import env_value, require_env_values  # type: ignore[no-redef]
    from changelog_llm_generation import (  # type: ignore[no-redef]
        generate_breaking_changes_output,
        generate_grouped_changelog_output,
        generate_release_notes_body_output,
    )
    from changelog_llm_outputs import (  # type: ignore[no-redef]
        LLM_CALL_BREAKING_CHANGES,
        LLM_CALL_CHANGELOG_COPY,
        LLM_CALL_GROUPED_CHANGELOG_ENTRIES,
        LLM_CALL_MARKDOWN_SECTION,
        LLM_CALL_RELEASE_NOTES_BODY,
        Audience,
        BreakingChangesOutput,
        ChangelogCopy,
        ChangelogLabel,
        GroupedChangelogEntry,
        GroupedChangelogOutput,
        MarkdownSection,
    )
    from changelog_llm_providers import (  # type: ignore[no-redef]
        DEFAULT_ANTHROPIC_MODEL,
        DEFAULT_LLM_PROVIDER,
        DEFAULT_OPENAI_MODEL,
        LLM_MODEL_ENV,
        LLM_PROVIDER_ENV,
        LLM_PROVIDER_OPENAI,
        Anthropic,
        AnthropicStructuredLLMClient,
        LLMOutputValidationError,
        LLMProviderNonRetryableError,
        LLMProviderRetryableError,
        OpenAI,
        OpenAIStructuredLLMClient,
        StructuredLLMClient,
        build_openai_structured_llm_client,
        llm_retryable,
        openai_response_has_refusal,
    )
    from changelog_prompts import (  # type: ignore[no-redef]
        build_breaking_changes_prompt,
        build_changelog_copy_prompt,
        build_grouped_changelog_entries_prompt,
        build_markdown_section_prompt,
        build_release_notes_body_prompt,
    )
    from changelog_rendering import (  # type: ignore[no-redef]
        render_breaking_section,
        render_release_footer,
        render_release_header,
        render_release_notes_section,
        update_markdown_file,
    )
    from changelog_schema_validation import (  # type: ignore[no-redef]
        validate_changelog,
        validate_changelog_data,
    )
    from changelog_validators import (  # type: ignore[no-redef]
        GroupedChangelogSemanticError,
        assert_unique_grouped_pr_numbers,
        build_grouped_retry_feedback,
        contains_forbidden_pr_reference,
        format_grouped_attempt_summaries,
        format_repo_qualified_pr,
        markdown_pr_link_pattern,
        missing_markdown_pr_links,
        summarize_grouped_changelog_output,
        validate_breaking_changes_output,
        validate_grouped_changelog_output,
        validate_release_notes_body_output,
    )

try:
    from scripts.consumed_sources import (
        CONSUMED_SOURCE_STATE_FILE,
        ConsumedPR,
        ConsumedSourceState,
        ConsumedTargetState,
        ConsumedWindow,
        format_source_window,
        mark_consumed_after_success,
        read_consumed_source_state,
        target_state_key,
        write_consumed_source_state,
    )
    from scripts.source_windows import (
        SKIP_REASON_ALREADY_CONSUMED_WINDOW,
        MultiSourceCollectionResult,
        collect_multi_source_prs as _collect_multi_source_prs,
        format_source_window_body,
    )
    from scripts.workflow_result import (
        ChangelogWorkflowResult,
        NeedsAttentionItem,
        clear_changelog_workflow_result,
        format_breaking_changes_output,
        format_needs_attention_output,
        get_changelog_workflow_result_path,
        write_changelog_workflow_result,
    )
except ModuleNotFoundError:  # pragma: no cover - direct `uv run scripts/update_changelog.py`
    from consumed_sources import (  # type: ignore[no-redef]
        CONSUMED_SOURCE_STATE_FILE,
        ConsumedPR,
        ConsumedSourceState,
        ConsumedTargetState,
        ConsumedWindow,
        format_source_window,
        mark_consumed_after_success,
        read_consumed_source_state,
        target_state_key,
        write_consumed_source_state,
    )
    from source_windows import (  # type: ignore[no-redef]
        SKIP_REASON_ALREADY_CONSUMED_WINDOW,
        MultiSourceCollectionResult,
        collect_multi_source_prs as _collect_multi_source_prs,
        format_source_window_body,
    )
    from workflow_result import (  # type: ignore[no-redef]
        ChangelogWorkflowResult,
        NeedsAttentionItem,
        clear_changelog_workflow_result,
        format_breaking_changes_output,
        format_needs_attention_output,
        get_changelog_workflow_result_path,
        write_changelog_workflow_result,
    )

IMAGE_STATE_FILE = Path(".image_state")
MAX_IMAGE_NUMBER = 49

# Placeholder URLs that pass schema validation but are clearly marked for review
class ImageState(BaseModel):
    last_image_number: int = Field(default=0, ge=0, le=MAX_IMAGE_NUMBER)
    last_release_tag: Optional[str] = None
    last_markdown_file: Optional[str] = None
    updated_at: Optional[str] = None


llm_client: Optional[StructuredLLMClient] = None

OPENAI_SHADOW_MODE_ENV = "CHANGELOG_OPENAI_SHADOW_MODE"
OPENAI_SHADOW_MODEL_ENV = "CHANGELOG_OPENAI_SHADOW_MODEL"
OPENAI_SHADOW_WIDGET_COMMENT_ENV = "CHANGELOG_OPENAI_SHADOW_WIDGET_COMMENT"
OPENAI_SHADOW_RELEASE_NOTES_COMMENT_ENV = "CHANGELOG_OPENAI_SHADOW_RELEASE_NOTES_COMMENT"
DEFAULT_OPENAI_SHADOW_WIDGET_COMMENT = "openai-shadow-widget-comment.md"
DEFAULT_OPENAI_SHADOW_RELEASE_NOTES_COMMENT = "openai-shadow-release-notes-comment.md"
OPENAI_SHADOW_WIDGET_MARKER = "<!-- zenml-changelog-openai-shadow-widget -->"
OPENAI_SHADOW_RELEASE_NOTES_MARKER = "<!-- zenml-changelog-openai-shadow-release-notes -->"


def ensure_required_env(vars_list: List[str]) -> Dict[str, str]:
    """Backward-compatible wrapper for required env parsing.

    Blank values now behave like missing values.
    """
    return require_env_values(vars_list)


def build_structured_llm_client_from_env() -> StructuredLLMClient:
    """Build the configured LLM client, preserving old monkeypatch seams.

    The implementation lives in changelog_llm_providers. Syncing these globals
    keeps older tests/callers that patch update_changelog.Anthropic or
    update_changelog.OpenAI working after the module split.
    """
    _llm_providers.Anthropic = Anthropic
    _llm_providers.OpenAI = OpenAI
    return _llm_providers.build_structured_llm_client_from_env()


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

def _model_dump(model: BaseModel) -> Dict[str, Any]:
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()  # type: ignore[attr-defined]



def write_image_state(state: ImageState, path: Path = IMAGE_STATE_FILE) -> None:
    path.write_text(json.dumps(_model_dump(state), indent=2, sort_keys=True) + "\n")



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

def collect_multi_source_prs(
    gh: Github,
    trigger_repo: str,
    trigger_release_tag: str,
    consumed_state: ConsumedSourceState,
) -> MultiSourceCollectionResult:
    return _collect_multi_source_prs(
        gh=gh,
        trigger_repo=trigger_repo,
        trigger_release_tag=trigger_release_tag,
        consumed_state=consumed_state,
        repo_config=REPO_CONFIG,
        breaking_change_labels=BREAKING_CHANGE_LABELS,
        find_latest_release_tag=find_latest_release_tag,
        find_previous_tag=find_previous_tag,
        get_release_window=get_release_window,
        search_merged_prs=search_merged_prs,
        dedupe_prs_by_number=dedupe_prs_by_number,
    )


def require_llm_client() -> StructuredLLMClient:
    """Return the configured structured-output LLM client."""
    if llm_client is not None:
        return llm_client
    raise RuntimeError("LLM client not initialized")


@llm_retryable()
def llm_generate_changelog_copy(pr_title: str, pr_body: str, pr_url: str, repo_type: str) -> ChangelogCopy:
    # NOTE: This helper is primarily intended for ad-hoc or manual usage.
    # The main automation flow uses llm_generate_grouped_changelog_entries to create grouped entries per release.
    prompt = build_changelog_copy_prompt(pr_title, pr_body, pr_url, repo_type)
    return require_llm_client().parse_structured_output(
        prompt=prompt,
        output_model=ChangelogCopy,
        max_output_tokens=700,
        call_name=LLM_CALL_CHANGELOG_COPY,
    )


@llm_retryable()
def llm_generate_grouped_changelog_entries(
    prs: List[Dict[str, Any]],
    source_repo: str,
    retry_feedback: Optional[str] = None,
) -> GroupedChangelogOutput:
    return generate_grouped_changelog_output(
        client=require_llm_client(),
        prs=prs,
        source_repo=source_repo,
        retry_feedback=retry_feedback,
    )


@llm_retryable()
def llm_generate_breaking_changes_bullets(
    breaking_prs: List[Dict[str, Any]],
    source_repo: str,
    include_pr_links: bool,
) -> List[str]:
    """Generate user-facing bullet points summarizing breaking changes from PRs."""
    output, warnings = generate_breaking_changes_output(
        client=require_llm_client(),
        breaking_prs=breaking_prs,
        source_repo=source_repo,
        include_pr_links=include_pr_links,
    )
    for warning in warnings:
        print(f"Warning: {warning}")
    return output.bullets


@llm_retryable()
def llm_generate_release_notes_body(
    prs: List[Dict[str, Any]],
    source_repo: str,
    include_pr_links: bool,
) -> str:
    """Generate the body portion of release notes (no header, footer, or breaking section)."""
    output, warnings = generate_release_notes_body_output(
        client=require_llm_client(),
        prs=prs,
        source_repo=source_repo,
        include_pr_links=include_pr_links,
    )
    for warning in warnings:
        print(f"Warning: {warning}")
    return output.content


@llm_retryable()
def llm_generate_markdown_section(
    prs: List[Dict[str, Any]],
    release_tag: str,
    release_url: str,
    published_at: str,
    source_repo: str,
    image_number: int,
) -> str:
    prompt = build_markdown_section_prompt(
        prs=prs,
        release_tag=release_tag,
        release_url=release_url,
        published_at=published_at,
        source_repo=source_repo,
        image_number=image_number,
    )
    output = require_llm_client().parse_structured_output(
        prompt=prompt,
        output_model=MarkdownSection,
        max_output_tokens=2000,
        call_name=LLM_CALL_MARKDOWN_SECTION,
    )
    return output.content


def is_short_body(pr_body: str, threshold: int = 50) -> bool:
    return len((pr_body or "").strip()) < threshold

def collect_needs_attention(
    prs: List[Dict[str, Any]],
    threshold: int = 50,
) -> List[NeedsAttentionItem]:
    """Identify PRs with insufficient bodies that should be highlighted for manual review."""
    needs_attention: List[NeedsAttentionItem] = []
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


def generate_valid_grouped_changelog_entries(
    prs: List[Dict[str, Any]],
    source_repo: str,
    published_at: str,
    starting_id: int,
    max_attempts: int = 3,
) -> List[Dict[str, Any]]:
    """Generate grouped changelog entries, retrying only semantic PR assignment errors."""
    assert_unique_grouped_pr_numbers(prs)

    retry_feedback: Optional[str] = None
    attempt_errors: List[GroupedChangelogSemanticError] = []

    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            print(
                "Retrying grouped changelog generation after semantic validation failure "
                f"(attempt {attempt}/{max_attempts})"
            )

        grouped_output = llm_generate_grouped_changelog_entries(
            prs=prs,
            source_repo=source_repo,
            retry_feedback=retry_feedback,
        )

        try:
            return build_grouped_changelog_entries(
                grouped_output=grouped_output,
                prs=prs,
                source_repo=source_repo,
                published_at=published_at,
                starting_id=starting_id,
            )
        except GroupedChangelogSemanticError as error:
            attempt_errors.append(error)
            print(
                f"Grouped changelog semantic validation failed on attempt {attempt}/{max_attempts}: "
                + "; ".join(error.details)
            )
            retry_feedback = build_grouped_retry_feedback(error)

    raise RuntimeError(
        f"Grouped changelog generation failed semantic validation after {max_attempts} attempts.\n\n"
        f"{format_grouped_attempt_summaries(attempt_errors)}\n\n"
        "No changelog.json, markdown, or .image_state updates were written."
    )


def openai_shadow_mode_enabled() -> bool:
    """Return whether OpenAI shadow comments should be generated."""
    return (env_value(OPENAI_SHADOW_MODE_ENV) or "").lower() in {"1", "true", "yes", "on"}


def openai_shadow_comment_paths() -> tuple[Path, Path]:
    """Return configured shadow comment paths, with stable workflow defaults."""
    widget_path = Path(env_value(OPENAI_SHADOW_WIDGET_COMMENT_ENV) or DEFAULT_OPENAI_SHADOW_WIDGET_COMMENT)
    release_notes_path = Path(
        env_value(OPENAI_SHADOW_RELEASE_NOTES_COMMENT_ENV)
        or DEFAULT_OPENAI_SHADOW_RELEASE_NOTES_COMMENT
    )
    return widget_path, release_notes_path


def unsafe_shadow_comment_path_reason(path: Path) -> str | None:
    """Return a reason when a shadow comment path could overwrite production artifacts."""
    return unsafe_relative_artifact_path_reason(
        path,
        repo_root=Path.cwd(),
        extra_production_relative_paths={"changelog_workflow_result.json"},
    )


def _write_shadow_comment(path: Path, content: str) -> None:
    """Write a shadow comment file, logging instead of failing production."""
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as error:
        print(f"Failed to write OpenAI shadow comment {path}: {error}")


def _dump_json(value: Any) -> str:
    """Serialize Pydantic models or normal Python data for PR comments."""
    if isinstance(value, BaseModel):
        value = _model_dump(value)
    return json.dumps(value, indent=2, sort_keys=True)


def _fenced_block(language: str, content: str) -> str:
    """Render a safe fenced block for generated model text."""
    safe_content = content.replace("```", "`\u200b``")
    return f"```{language}\n{safe_content.rstrip()}\n```"


def _shadow_success_section(output_type: str, language: str, content: str) -> str:
    return (
        f"### Output type: `{output_type}`\n\n"
        "- Status: `passed`\n\n"
        f"{_fenced_block(language, content)}\n"
    )


def _shadow_failure_section(output_type: str, error: Exception) -> str:
    return (
        f"### Output type: `{output_type}`\n\n"
        "- Status: `failed`\n\n"
        f"{_fenced_block('text', f'{type(error).__name__}: {error}')}\n"
    )


def _shadow_header(marker: str, model: str) -> str:
    return (
        f"{marker}\n\n"
        "## OpenAI shadow-mode output\n\n"
        f"- Provider: `{LLM_PROVIDER_OPENAI}`\n"
        f"- Model: `{model}`\n\n"
        "This is a review aid generated by the shadow provider. It is not used to "
        "write `changelog.json`, release-note markdown, `.image_state`, or "
        "`.consumed_sources_state`.\n\n"
    )


def build_openai_shadow_client() -> OpenAIStructuredLLMClient | None:
    """Build an OpenAI client for shadow mode, or return None when safely skipped."""
    api_key = env_value("OPENAI_API_KEY")
    if api_key is None:
        print("OpenAI shadow mode enabled, but OPENAI_API_KEY is missing or blank. Skipping shadow comments.")
        return None
    if OpenAI is None:
        print("OpenAI shadow mode enabled, but the openai package is unavailable. Skipping shadow comments.")
        return None
    model = env_value(OPENAI_SHADOW_MODEL_ENV) or DEFAULT_OPENAI_MODEL
    _llm_providers.OpenAI = OpenAI
    return build_openai_structured_llm_client(api_key=api_key, model=model)


def write_openai_shadow_comments(
    *,
    grouping_prs: List[Dict[str, Any]],
    body_prs: List[Dict[str, Any]],
    breaking_prs: List[Dict[str, Any]],
    source_repo: str,
    published_at: str,
    starting_id: int,
    include_pr_links: bool,
) -> None:
    """Generate OpenAI shadow output files without mutating production artifacts.

    This is deliberately separate from the global production `llm_client`. If it
    fails, reviewers get a labeled failure comment where possible, but the
    Anthropic/default production path continues unchanged.
    """
    if not openai_shadow_mode_enabled():
        return

    widget_path, release_notes_path = openai_shadow_comment_paths()
    unsafe_paths = [
        f"{path}: {reason}"
        for path in (widget_path, release_notes_path)
        if (reason := unsafe_shadow_comment_path_reason(path)) is not None
    ]
    if unsafe_paths:
        print(
            "OpenAI shadow mode enabled, but configured comment paths are unsafe. "
            "Skipping shadow comments: " + "; ".join(unsafe_paths)
        )
        return

    shadow_client = build_openai_shadow_client()
    if shadow_client is None:
        return

    model = shadow_client.model

    try:
        grouped_output = generate_grouped_changelog_output(
            client=shadow_client,
            prs=grouping_prs,
            source_repo=source_repo,
        )
        grouped_entries = build_grouped_changelog_entries(
            grouped_output=grouped_output,
            prs=grouping_prs,
            source_repo=source_repo,
            published_at=published_at,
            starting_id=starting_id,
        )
        widget_section = _shadow_success_section(
            "dashboard grouped changelog entries",
            "json",
            _dump_json(
                {
                    "raw_grouped_output": _model_dump(grouped_output),
                    "schema_entries": grouped_entries,
                }
            ),
        )
    except Exception as error:  # noqa: BLE001 - shadow failures must not fail production
        print(f"OpenAI shadow widget generation failed: {error}")
        widget_section = _shadow_failure_section("dashboard grouped changelog entries", error)

    _write_shadow_comment(widget_path, _shadow_header(OPENAI_SHADOW_WIDGET_MARKER, model) + widget_section)

    release_sections: List[str] = []
    try:
        breaking_output, _warnings = generate_breaking_changes_output(
            client=shadow_client,
            breaking_prs=breaking_prs,
            source_repo=source_repo,
            include_pr_links=include_pr_links,
        )
        release_sections.append(
            _shadow_success_section("breaking_changes", "json", _dump_json(breaking_output))
        )
    except Exception as error:  # noqa: BLE001 - shadow failures must not fail production
        print(f"OpenAI shadow breaking-change generation failed: {error}")
        release_sections.append(_shadow_failure_section("breaking_changes", error))

    try:
        body_output, _warnings = generate_release_notes_body_output(
            client=shadow_client,
            prs=body_prs,
            source_repo=source_repo,
            include_pr_links=include_pr_links,
        )
        release_sections.append(
            _shadow_success_section("release_notes_body", "md", body_output.content or "<empty>")
        )
    except Exception as error:  # noqa: BLE001 - shadow failures must not fail production
        print(f"OpenAI shadow release-note body generation failed: {error}")
        release_sections.append(_shadow_failure_section("release_notes_body", error))

    _write_shadow_comment(
        release_notes_path,
        _shadow_header(OPENAI_SHADOW_RELEASE_NOTES_MARKER, model) + "\n".join(release_sections),
    )


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
    global llm_client
    llm_client = None

    workflow_result_path = get_changelog_workflow_result_path()
    clear_changelog_workflow_result(workflow_result_path)

    env = require_env_values(["SOURCE_REPO", "RELEASE_TAG", "GITHUB_TOKEN"])
    source_repo = env["SOURCE_REPO"]
    if source_repo not in REPO_CONFIG:
        raise RuntimeError(f"Repository {source_repo} is not configured for changelog updates")
    github_token = env_value("PRIVATE_REPO_TOKEN") or env["GITHUB_TOKEN"]
    gh = Github(auth=Auth.Token(github_token))

    # Fetch release info from GitHub if not provided (for manual triggers)
    release_url = env_value("RELEASE_URL") or ""
    published_at = env_value("PUBLISHED_AT") or ""
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

    consumed_state = read_consumed_source_state()
    collection = collect_multi_source_prs(
        gh=gh,
        trigger_repo=source_repo,
        trigger_release_tag=env["RELEASE_TAG"],
        consumed_state=consumed_state,
    )
    source_windows_body = format_source_window_body(collection)
    if source_windows_body:
        print("Source windows:")
        print(source_windows_body)

    release_notes_prs = collection.release_notes_prs
    print(f"Found {len(release_notes_prs)} PRs with release-notes label across all sources")

    breaking_prs = collection.breaking_prs
    print(f"Found {len(breaking_prs)} PRs with breaking-change labels across all sources")

    major_bump = is_major_bump(primary_previous_tag, env["RELEASE_TAG"])
    if major_bump:
        print("Detected major version bump - will force Breaking Changes section")

    if not release_notes_prs and not breaking_prs:
        print("No release-notes or breaking-change PRs found for this release. Nothing to do.")
        write_changelog_workflow_result(
            ChangelogWorkflowResult(
                has_changes=False,
                markdown_file=config["markdown_file"],
                breaking_changes="",
                needs_attention="",
                source_windows=source_windows_body,
            ),
            workflow_result_path,
        )
        raise SystemExit(0)

    if not source_windows_body.strip():
        raise RuntimeError(
            "Release-note or breaking-change PRs were collected, but the source-window body is empty. "
            "Refusing to write changelog artifacts without source-window metadata."
        )

    llm_client = build_structured_llm_client_from_env()

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

    # Use a single valid grouping to create 2-3 thematic changelog entries.
    # Semantically invalid groupings are retried before any repository files are written.
    new_entries = generate_valid_grouped_changelog_entries(
        prs=grouping_prs,
        source_repo=source_repo,
        published_at=published_at,
        starting_id=starting_id,
    )

    for entry in new_entries:
        print(f"Created grouped changelog entry #{entry['id']}: {entry['title']}")

    markdown_file = config["markdown_file"]
    body = llm_generate_release_notes_body(body_prs, source_repo, include_pr_links) if body_prs else ""

    write_openai_shadow_comments(
        grouping_prs=grouping_prs,
        body_prs=body_prs,
        breaking_prs=breaking_prs,
        source_repo=source_repo,
        published_at=published_at,
        starting_id=starting_id,
        include_pr_links=include_pr_links,
    )

    new_entries.sort(key=lambda entry: entry["id"], reverse=True)
    updated_changelog = new_entries + existing_changelog
    schema_path = Path(__file__).resolve().parents[1] / "changelog_schema" / "announcement-schema.json"
    validate_changelog_data(updated_changelog, schema_path)
    changelog_path.write_text(json.dumps(updated_changelog, indent=2) + "\n")
    validate_changelog(changelog_path, schema_path)

    image_number = get_next_image_number(
        release_tag=env["RELEASE_TAG"],
        markdown_file=markdown_file,
    )
    md_section = render_release_notes_section(
        release_tag=env["RELEASE_TAG"],
        published_at=published_at,
        image_number=image_number,
        source_repo=source_repo,
        release_url=release_url,
        breaking_bullets=breaking_bullets,
        body=body,
        force_breaking_placeholder=False,
        is_major_bump=major_bump,
    )

    update_markdown_file(Path(markdown_file), md_section)

    consumed_state = mark_consumed_after_success(
        state=consumed_state,
        trigger_repo=source_repo,
        markdown_file=markdown_file,
        trigger_release_tag=env["RELEASE_TAG"],
        collection=collection,
        now=datetime.now(timezone.utc),
    )
    write_consumed_source_state(consumed_state)

    print(
        f"Updated changelog.json (+{len(new_entries)} entries), "
        f"{config['markdown_file']} (image {image_number}), and "
        f"{CONSUMED_SOURCE_STATE_FILE}."
    )

    write_changelog_workflow_result(
        ChangelogWorkflowResult(
            has_changes=True,
            markdown_file=markdown_file,
            breaking_changes=format_breaking_changes_output(
                breaking_bullets,
                is_major_bump=major_bump,
            ),
            needs_attention=format_needs_attention_output(needs_attention),
            source_windows=source_windows_body,
        ),
        workflow_result_path,
    )


if __name__ == "__main__":
    main()
