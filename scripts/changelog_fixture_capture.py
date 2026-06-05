#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Turn real ZenML releases into evaluation fixtures.

This reuses the same GitHub PR-collection functions as the release automation
(``find_previous_tag``, ``get_release_window``, ``search_merged_prs``,
``dedupe_prs_by_number``) but, instead of writing production artifacts, it
assembles an ``EvalFixture``-shaped dict so the evaluation harness can run real
release content through the candidate models.

Every function takes its GitHub-touching collaborators as parameters
(dependency injection), so the logic is testable with fakes and never makes a
live network call in the test suite.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Optional, Sequence

from scripts import changelog_config as cfg
from scripts.consumed_sources import ConsumedSourceState
from scripts.source_windows import collect_multi_source_prs

FIXTURE_PR_FIELDS = ("number", "title", "url", "author", "body", "labels", "repo")

RELEASE_NOTES_LABEL = "release-notes"

DEFAULT_STARTING_ID = 1000
DEFAULT_IMAGE_NUMBER = 1


class FixtureCaptureError(RuntimeError):
    """Raised for capture configuration errors."""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "x"


def strip_pr_for_fixture(pr: dict) -> dict:
    """Keep only the fields fixtures store, dropping non-serializable extras (merged_at)."""
    stripped = {field: pr.get(field) for field in FIXTURE_PR_FIELDS}
    stripped["labels"] = list(pr.get("labels", []))
    return stripped


def _semver(tag: Optional[str]) -> Optional[tuple[int, int, int]]:
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", tag or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def is_major_bump(previous_tag: Optional[str], current_tag: str) -> bool:
    current = _semver(current_tag)
    previous = _semver(previous_tag)
    if current is None or previous is None:
        return False
    return current[0] > previous[0]


def fixture_id_for(source_repo: str, release_tag: str, prefix: str = "real") -> str:
    repo_slug = source_repo.split("/")[-1]
    return f"{prefix}-{repo_slug}-{_slug(release_tag)}"


def build_fixture_dict(
    *,
    source_repo: str,
    release_tag: str,
    release_url: str,
    published_at: str,
    previous_tag: Optional[str],
    release_notes_prs: Sequence[dict],
    breaking_prs: Sequence[dict],
    description: Optional[str] = None,
    starting_id: int = DEFAULT_STARTING_ID,
    image_number: int = DEFAULT_IMAGE_NUMBER,
) -> dict:
    """Assemble an EvalFixture-shaped dict from already-collected PRs and metadata."""
    return {
        "fixture_id": fixture_id_for(source_repo, release_tag),
        "description": description or f"Real {source_repo} release {release_tag}.",
        "source_repo": source_repo,
        "release_tag": release_tag,
        "release_url": release_url,
        "published_at": published_at,
        "image_number": image_number,
        "starting_id": starting_id,
        "major_bump": is_major_bump(previous_tag, release_tag),
        "expected_hard_gate_status": "pass",
        "expected_failure": None,
        "release_notes_prs": [strip_pr_for_fixture(pr) for pr in release_notes_prs],
        "breaking_prs": [strip_pr_for_fixture(pr) for pr in breaking_prs],
        "offline_candidates": [],
    }


SearchMergedPRs = Callable[[Any, str, str, datetime, datetime, Optional[str]], list[dict]]
DedupePRs = Callable[[list[dict]], list[dict]]
FindPreviousTag = Callable[[Any, str, str], Optional[str]]
FindLatestReleaseTag = Callable[[Any, str], Optional[str]]
GetReleaseWindow = Callable[[Any, str, Optional[str], str], tuple[datetime, datetime]]
GetReleaseMetadata = Callable[[Any, str, str], tuple[str, str]]


def collect_bundled_window_prs(
    *,
    gh: Any,
    sources: Sequence[dict],
    since_date: datetime,
    until_date: datetime,
    breaking_change_labels: Sequence[str],
    search_merged_prs: SearchMergedPRs,
    dedupe_prs_by_number: DedupePRs,
) -> tuple[list[dict], list[dict]]:
    """Collect release-note and breaking PRs across all bundled source repos in one window."""
    release_notes: list[dict] = []
    breaking: list[dict] = []
    for source in sources:
        repo = source["repo"]
        branch = source.get("default_branch", "main")
        release_notes.extend(
            search_merged_prs(gh, repo, branch, since_date, until_date, RELEASE_NOTES_LABEL)
        )
        for label in breaking_change_labels:
            breaking.extend(search_merged_prs(gh, repo, branch, since_date, until_date, label))
    return dedupe_prs_by_number(release_notes), dedupe_prs_by_number(breaking)


def capture_release_fixture(
    *,
    gh: Any,
    trigger_repo: str,
    release_tag: str,
    repo_config: dict,
    breaking_change_labels: Sequence[str],
    find_latest_release_tag: FindLatestReleaseTag,
    find_previous_tag: FindPreviousTag,
    get_release_window: GetReleaseWindow,
    search_merged_prs: SearchMergedPRs,
    dedupe_prs_by_number: DedupePRs,
    get_release_metadata: GetReleaseMetadata,
    starting_id: int = DEFAULT_STARTING_ID,
    image_number: int = DEFAULT_IMAGE_NUMBER,
) -> dict:
    """Capture one real release (with its bundled sources) into a fixture dict."""
    config = repo_config.get(trigger_repo)
    if config is None:
        raise FixtureCaptureError(f"{trigger_repo} is not configured for changelog updates.")
    sources = config.get("sources", [])
    if not sources:
        raise FixtureCaptureError(f"{trigger_repo} has no bundled sources configured.")

    previous_tag = find_previous_tag(gh, trigger_repo, release_tag)
    collection = collect_multi_source_prs(
        gh=gh,
        trigger_repo=trigger_repo,
        trigger_release_tag=release_tag,
        consumed_state=ConsumedSourceState(),
        repo_config=repo_config,
        breaking_change_labels=list(breaking_change_labels),
        find_latest_release_tag=find_latest_release_tag,
        find_previous_tag=find_previous_tag,
        get_release_window=get_release_window,
        search_merged_prs=search_merged_prs,
        dedupe_prs_by_number=dedupe_prs_by_number,
    )
    release_notes_prs = collection.release_notes_prs
    breaking_prs = collection.breaking_prs
    release_url, published_at = get_release_metadata(gh, trigger_repo, release_tag)
    bundled = ", ".join(source["repo"].split("/")[-1] for source in sources)
    return build_fixture_dict(
        source_repo=trigger_repo,
        release_tag=release_tag,
        release_url=release_url,
        published_at=published_at,
        previous_tag=previous_tag,
        release_notes_prs=release_notes_prs,
        breaking_prs=breaking_prs,
        description=f"Real {trigger_repo} release {release_tag} (bundles {bundled}).",
        starting_id=starting_id,
        image_number=image_number,
    )


def resolve_last_n_tags(
    *,
    gh: Any,
    trigger_repo: str,
    count: int,
    find_latest_release_tag: FindLatestReleaseTag,
    find_previous_tag: FindPreviousTag,
) -> list[str]:
    """Walk back from the latest release tag, returning up to ``count`` tags newest-first."""
    tags: list[str] = []
    tag = find_latest_release_tag(gh, trigger_repo)
    while tag and len(tags) < count:
        tags.append(tag)
        tag = find_previous_tag(gh, trigger_repo, tag)
    return tags


def github_release_metadata(gh: Any, repo_name: str, tag: str) -> tuple[str, str]:
    """Default ``get_release_metadata`` using a live GitHub client (not used in tests)."""
    repo = gh.get_repo(repo_name)
    release = repo.get_release(cfg.with_prefix(repo_name, tag))
    published = release.published_at or release.created_at
    published_iso = published.strftime("%Y-%m-%dT%H:%M:%SZ") if published else ""
    return release.html_url, published_iso
