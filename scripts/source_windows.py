from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

from github import Github
from pydantic import BaseModel, Field

try:
    from scripts.consumed_sources import (
        ConsumedSourceState,
        ConsumedTargetState,
        find_consumed_window,
        format_source_window,
        get_consumed_target_state,
        is_pr_consumed,
        pr_key_from_dict,
    )
except ModuleNotFoundError:  # pragma: no cover - direct `uv run scripts/update_changelog.py`
    from consumed_sources import (  # type: ignore[no-redef]
        ConsumedSourceState,
        ConsumedTargetState,
        find_consumed_window,
        format_source_window,
        get_consumed_target_state,
        is_pr_consumed,
        pr_key_from_dict,
    )

SKIP_REASON_NO_RELEASES_FOUND = "no_releases_found"
SKIP_REASON_ALREADY_CONSUMED_WINDOW = "already_consumed_window"
SkipReason = Literal["no_releases_found", "already_consumed_window"]

FindLatestReleaseTag = Callable[[Github, str], Optional[str]]
FindPreviousTag = Callable[[Github, str, str], Optional[str]]
GetReleaseWindow = Callable[[Github, str, Optional[str], str], Tuple[datetime, datetime]]
SearchMergedPRs = Callable[
    [Github, str, str, datetime, datetime, Optional[str]],
    List[Dict[str, Any]],
]
DedupePRs = Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]


class SourceReleaseWindow(BaseModel):
    source_repo: str
    base_branch: str
    previous_tag: Optional[str] = None
    current_tag: str
    since_date: datetime
    until_date: datetime
    is_primary: bool = False


class SkippedSourceWindow(BaseModel):
    source_repo: str
    previous_tag: Optional[str] = None
    current_tag: Optional[str] = None
    reason: SkipReason
    consumed_by_release_tag: Optional[str] = None


class SourceWindowCollection(BaseModel):
    window: SourceReleaseWindow
    release_notes_prs: List[Dict[str, Any]] = Field(default_factory=list)
    breaking_prs: List[Dict[str, Any]] = Field(default_factory=list)
    filtered_pr_keys: List[str] = Field(default_factory=list)


class MultiSourceCollectionResult(BaseModel):
    included_windows: List[SourceWindowCollection] = Field(default_factory=list)
    skipped_windows: List[SkippedSourceWindow] = Field(default_factory=list)
    release_notes_prs: List[Dict[str, Any]] = Field(default_factory=list)
    breaking_prs: List[Dict[str, Any]] = Field(default_factory=list)


def _filter_consumed_prs(
    prs: List[Dict[str, Any]],
    target_state: Optional[ConsumedTargetState],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    kept: List[Dict[str, Any]] = []
    filtered_keys: List[str] = []
    for pr in prs:
        key = pr_key_from_dict(pr)
        if is_pr_consumed(target_state, key):
            filtered_keys.append(key)
            continue
        kept.append(pr)
    return kept, filtered_keys


def resolve_source_window(
    gh: Github,
    source: Dict[str, Any],
    primary_source: str,
    trigger_release_tag: str,
    find_latest_release_tag: FindLatestReleaseTag,
    find_previous_tag: FindPreviousTag,
    get_release_window: GetReleaseWindow,
) -> Tuple[Optional[SourceReleaseWindow], Optional[SkippedSourceWindow]]:
    source_repo = source["repo"]
    is_primary = source_repo == primary_source

    if is_primary:
        current_tag = trigger_release_tag
    else:
        current_tag = find_latest_release_tag(gh, source_repo)
        if current_tag is None:
            return None, SkippedSourceWindow(
                source_repo=source_repo,
                reason=SKIP_REASON_NO_RELEASES_FOUND,
            )

    previous_tag = find_previous_tag(gh, source_repo, current_tag)
    since_date, until_date = get_release_window(
        gh,
        source_repo,
        previous_tag,
        current_tag,
    )
    return SourceReleaseWindow(
        source_repo=source_repo,
        base_branch=source.get("default_branch", "main"),
        previous_tag=previous_tag,
        current_tag=current_tag,
        since_date=since_date,
        until_date=until_date,
        is_primary=is_primary,
    ), None


def collect_window_prs(
    gh: Github,
    window: SourceReleaseWindow,
    target_state: Optional[ConsumedTargetState],
    breaking_change_labels: List[str],
    search_merged_prs: SearchMergedPRs,
    dedupe_prs_by_number: DedupePRs,
) -> SourceWindowCollection:
    release_note_prs = search_merged_prs(
        gh,
        window.source_repo,
        window.base_branch,
        window.since_date,
        window.until_date,
        "release-notes",
    )
    release_note_prs, release_note_filtered = _filter_consumed_prs(
        release_note_prs,
        target_state,
    )

    breaking_prs_for_window: List[Dict[str, Any]] = []
    breaking_filtered: List[str] = []
    for breaking_label in breaking_change_labels:
        source_breaking_prs = search_merged_prs(
            gh,
            window.source_repo,
            window.base_branch,
            window.since_date,
            window.until_date,
            breaking_label,
        )
        filtered_source_breaking_prs, filtered_keys = _filter_consumed_prs(
            source_breaking_prs,
            target_state,
        )
        breaking_prs_for_window.extend(filtered_source_breaking_prs)
        breaking_filtered.extend(filtered_keys)

    return SourceWindowCollection(
        window=window,
        release_notes_prs=dedupe_prs_by_number(release_note_prs),
        breaking_prs=dedupe_prs_by_number(breaking_prs_for_window),
        filtered_pr_keys=sorted(set(release_note_filtered + breaking_filtered)),
    )


def collect_multi_source_prs(
    gh: Github,
    trigger_repo: str,
    trigger_release_tag: str,
    consumed_state: ConsumedSourceState,
    repo_config: Dict[str, Dict[str, Any]],
    breaking_change_labels: List[str],
    find_latest_release_tag: FindLatestReleaseTag,
    find_previous_tag: FindPreviousTag,
    get_release_window: GetReleaseWindow,
    search_merged_prs: SearchMergedPRs,
    dedupe_prs_by_number: DedupePRs,
) -> MultiSourceCollectionResult:
    """Collect release-note and breaking-change PRs through one source-window path.

    Primary sources use the triggering release tag. Bundled sources keep the useful
    existing behavior of using their latest release, but each resolved source window
    is checked against the dedicated consumed-source ledger before PR search.

    A matched consumed window is finalized: it is skipped completely. This means
    PRs that gain a release-note/breaking label after the window was recorded are
    intentionally ignored instead of reopening already-published release notes.
    """
    config = repo_config.get(trigger_repo)
    if config is None:
        raise RuntimeError(f"Repository {trigger_repo} is not configured for changelog updates")

    sources = config.get("sources", [])
    if not sources:
        return MultiSourceCollectionResult()

    markdown_file = config["markdown_file"]
    target_state = get_consumed_target_state(
        state=consumed_state,
        trigger_repo=trigger_repo,
        markdown_file=markdown_file,
    )
    primary_source = sources[0]["repo"]

    result = MultiSourceCollectionResult()
    all_release_note_prs: List[Dict[str, Any]] = []
    all_breaking_prs: List[Dict[str, Any]] = []

    for source in sources:
        window, skipped_window = resolve_source_window(
            gh=gh,
            source=source,
            primary_source=primary_source,
            trigger_release_tag=trigger_release_tag,
            find_latest_release_tag=find_latest_release_tag,
            find_previous_tag=find_previous_tag,
            get_release_window=get_release_window,
        )
        if skipped_window is not None:
            result.skipped_windows.append(skipped_window)
            continue
        if window is None:
            continue

        consumed_window = find_consumed_window(
            target_state=target_state,
            source_repo=window.source_repo,
            previous_tag=window.previous_tag,
            current_tag=window.current_tag,
        )
        if consumed_window is not None:
            result.skipped_windows.append(
                SkippedSourceWindow(
                    source_repo=window.source_repo,
                    previous_tag=window.previous_tag,
                    current_tag=window.current_tag,
                    reason=SKIP_REASON_ALREADY_CONSUMED_WINDOW,
                    consumed_by_release_tag=consumed_window.consumed_by_release_tag,
                )
            )
            continue

        source_collection = collect_window_prs(
            gh=gh,
            window=window,
            target_state=target_state,
            breaking_change_labels=breaking_change_labels,
            search_merged_prs=search_merged_prs,
            dedupe_prs_by_number=dedupe_prs_by_number,
        )
        result.included_windows.append(source_collection)
        all_release_note_prs.extend(source_collection.release_notes_prs)
        all_breaking_prs.extend(source_collection.breaking_prs)

    result.release_notes_prs = dedupe_prs_by_number(all_release_note_prs)
    result.breaking_prs = dedupe_prs_by_number(all_breaking_prs)
    return result


def _format_source_window_lines(collection: MultiSourceCollectionResult) -> list[str]:
    lines: list[str] = []
    for source_collection in collection.included_windows:
        window = source_collection.window
        lines.append(
            "included "
            f"{window.source_repo} "
            f"{format_source_window(window.previous_tag, window.current_tag)} "
            f"release_notes={len(source_collection.release_notes_prs)} "
            f"breaking={len(source_collection.breaking_prs)} "
            f"filtered={len(source_collection.filtered_pr_keys)}"
        )
    for skipped_window in collection.skipped_windows:
        lines.append(
            "skipped "
            f"{skipped_window.source_repo} "
            f"{format_source_window(skipped_window.previous_tag, skipped_window.current_tag or '<none>')} "
            f"reason={skipped_window.reason} "
            f"consumed_by={skipped_window.consumed_by_release_tag or '<none>'}"
        )
    return lines


def format_source_window_body(collection: MultiSourceCollectionResult) -> str:
    return "\n".join(_format_source_window_lines(collection))

