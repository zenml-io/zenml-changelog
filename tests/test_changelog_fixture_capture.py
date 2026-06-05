from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import changelog_config as cfg
from scripts import changelog_fixture_capture as capture
from scripts import evaluate_changelog_llms as evaluator
from scripts import update_changelog as uc

DT_SINCE = datetime(2026, 1, 1, tzinfo=timezone.utc)
DT_UNTIL = datetime(2026, 2, 1, tzinfo=timezone.utc)
DASHBOARD_SINCE = datetime(2026, 1, 10, tzinfo=timezone.utc)
DASHBOARD_UNTIL = datetime(2026, 1, 20, tzinfo=timezone.utc)


def pr(number: int, repo: str, *, label: str = "release-notes", title: str | None = None) -> dict:
    return {
        "number": number,
        "title": title or f"PR {number}",
        "url": f"https://github.com/{repo}/pull/{number}",
        "author": "dev",
        "body": "body text",
        "labels": [label],
        "merged_at": datetime(2026, 1, 15, tzinfo=timezone.utc),
        "repo": repo,
    }


# ----------------------------------------------------------- pure assembly


def test_strip_pr_drops_merged_at_and_keeps_fixture_fields() -> None:
    stripped = capture.strip_pr_for_fixture(pr(101, "zenml-io/zenml"))
    assert stripped == {
        "number": 101,
        "title": "PR 101",
        "url": "https://github.com/zenml-io/zenml/pull/101",
        "author": "dev",
        "body": "body text",
        "labels": ["release-notes"],
        "repo": "zenml-io/zenml",
    }
    assert "merged_at" not in stripped


def test_is_major_bump() -> None:
    assert capture.is_major_bump("0.94.5", "1.0.0") is True
    assert capture.is_major_bump("0.94.5", "0.94.6") is False
    assert capture.is_major_bump(None, "0.94.6") is False


def test_build_fixture_dict_is_a_valid_eval_fixture() -> None:
    fixture = capture.build_fixture_dict(
        source_repo="zenml-io/zenml",
        release_tag="0.94.6",
        release_url="https://github.com/zenml-io/zenml/releases/tag/0.94.6",
        published_at="2026-02-01T00:00:00Z",
        previous_tag="0.94.5",
        release_notes_prs=[pr(101, "zenml-io/zenml")],
        breaking_prs=[],
    )

    assert fixture["fixture_id"] == "real-zenml-0-94-6"
    assert fixture["source_repo"] == "zenml-io/zenml"
    assert fixture["expected_hard_gate_status"] == "pass"
    assert fixture["offline_candidates"] == []
    assert "merged_at" not in fixture["release_notes_prs"][0]
    # Must load as a real eval fixture so the harness can run it.
    loaded = evaluator.EvalFixture.model_validate(fixture)
    assert loaded.fixture_id == "real-zenml-0-94-6"


# ----------------------------------------------------------- collection (DI)


def test_collect_bundled_window_prs_merges_both_sources() -> None:
    def fake_search(gh, repo, branch, since, until, label):
        if label != "release-notes":
            return []
        if repo == "zenml-io/zenml":
            return [pr(101, repo)]
        if repo == "zenml-io/zenml-dashboard":
            return [pr(7, repo)]
        return []

    sources = cfg.REPO_CONFIG["zenml-io/zenml"]["sources"]
    release_notes, breaking = capture.collect_bundled_window_prs(
        gh=None,
        sources=sources,
        since_date=DT_SINCE,
        until_date=DT_UNTIL,
        breaking_change_labels=cfg.BREAKING_CHANGE_LABELS,
        search_merged_prs=fake_search,
        dedupe_prs_by_number=uc.dedupe_prs_by_number,
    )

    assert {p["repo"] for p in release_notes} == {"zenml-io/zenml", "zenml-io/zenml-dashboard"}
    assert breaking == []


def test_collect_bundled_window_prs_collects_breaking_labels() -> None:
    def fake_search(gh, repo, branch, since, until, label):
        if label == "breaking-change" and repo == "zenml-io/zenml":
            return [pr(301, repo, label="breaking-change")]
        return []

    sources = cfg.REPO_CONFIG["zenml-io/zenml"]["sources"]
    release_notes, breaking = capture.collect_bundled_window_prs(
        gh=None,
        sources=sources,
        since_date=DT_SINCE,
        until_date=DT_UNTIL,
        breaking_change_labels=cfg.BREAKING_CHANGE_LABELS,
        search_merged_prs=fake_search,
        dedupe_prs_by_number=uc.dedupe_prs_by_number,
    )

    assert release_notes == []
    assert [p["number"] for p in breaking] == [301]


# ----------------------------------------------------------- capture one release (DI)


def test_capture_release_fixture_end_to_end() -> None:
    def fake_latest(gh, repo):
        return "0.13.15" if repo == "zenml-io/zenml-dashboard" else "0.94.6"

    def fake_previous(gh, repo, tag):
        if repo == "zenml-io/zenml-dashboard":
            return "0.13.14"
        return "0.94.5"

    def fake_window(gh, repo, previous, current):
        if repo == "zenml-io/zenml-dashboard":
            assert previous == "0.13.14"
            assert current == "0.13.15"
            return DASHBOARD_SINCE, DASHBOARD_UNTIL
        assert previous == "0.94.5"
        assert current == "0.94.6"
        return DT_SINCE, DT_UNTIL

    def fake_search(gh, repo, branch, since, until, label):
        if label != "release-notes":
            return []
        if repo == "zenml-io/zenml-dashboard":
            assert since == DASHBOARD_SINCE
            assert until == DASHBOARD_UNTIL
            return [pr(7, repo)]
        assert since == DT_SINCE
        assert until == DT_UNTIL
        return [pr(101, repo)]

    def fake_metadata(gh, repo, tag):
        return f"https://github.com/{repo}/releases/tag/{tag}", "2026-02-01T00:00:00Z"

    fixture = capture.capture_release_fixture(
        gh=None,
        trigger_repo="zenml-io/zenml",
        release_tag="0.94.6",
        repo_config=cfg.REPO_CONFIG,
        breaking_change_labels=cfg.BREAKING_CHANGE_LABELS,
        find_latest_release_tag=fake_latest,
        find_previous_tag=fake_previous,
        get_release_window=fake_window,
        search_merged_prs=fake_search,
        dedupe_prs_by_number=uc.dedupe_prs_by_number,
        get_release_metadata=fake_metadata,
    )

    assert fixture["fixture_id"] == "real-zenml-0-94-6"
    assert fixture["release_url"].endswith("0.94.6")
    assert fixture["published_at"] == "2026-02-01T00:00:00Z"
    assert {p["repo"] for p in fixture["release_notes_prs"]} == {
        "zenml-io/zenml",
        "zenml-io/zenml-dashboard",
    }
    evaluator.EvalFixture.model_validate(fixture)


# ----------------------------------------------------------- auto last-N (DI)


def test_resolve_last_n_tags_walks_back_through_previous_tags() -> None:
    chain = {"0.94.6": "0.94.5", "0.94.5": "0.94.4", "0.94.4": None}

    def fake_latest(gh, repo):
        return "0.94.6"

    def fake_previous(gh, repo, tag):
        return chain[tag]

    assert capture.resolve_last_n_tags(
        gh=None,
        trigger_repo="zenml-io/zenml",
        count=2,
        find_latest_release_tag=fake_latest,
        find_previous_tag=fake_previous,
    ) == ["0.94.6", "0.94.5"]

    # Asking for more than exist stops cleanly at the first release.
    assert capture.resolve_last_n_tags(
        gh=None,
        trigger_repo="zenml-io/zenml",
        count=10,
        find_latest_release_tag=fake_latest,
        find_previous_tag=fake_previous,
    ) == ["0.94.6", "0.94.5", "0.94.4"]


def test_capture_release_parser_accepts_last_and_tags() -> None:
    parsed = evaluator.build_parser().parse_args(
        ["capture-release", "--last", "3"]
    )
    assert parsed.command == "capture-release"
    assert parsed.last == 3
    # Real fixtures default to a dedicated subdir so they never land beside (and
    # break) the synthetic fixtures the offline tests scan.
    assert parsed.fixtures_dir.name == "real"
    assert parsed.fixtures_dir.parent.name == "changelog-evals"
