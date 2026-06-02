from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import update_changelog as uc


def make_pr(
    number: int,
    repo: str,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "number": number,
        "title": f"PR {number}",
        "labels": labels or [],
        "url": f"https://github.com/{repo}/pull/{number}",
        "body": f"Body for PR {number}",
        "repo": repo,
        "merged_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
    }


def pro_target_state(
    consumed_windows: list[uc.ConsumedWindow] | None = None,
    consumed_prs: dict[str, uc.ConsumedPR] | None = None,
) -> uc.ConsumedSourceState:
    markdown_file = "gitbook-release-notes/pro-control-plane.md"
    key = uc.target_state_key("zenml-io/zenml-cloud-api", markdown_file)
    return uc.ConsumedSourceState(
        targets={
            key: uc.ConsumedTargetState(
                trigger_repo="zenml-io/zenml-cloud-api",
                markdown_file=markdown_file,
                consumed_windows=consumed_windows or [],
                consumed_prs=consumed_prs or {},
            )
        }
    )


def consumed_ui_01314_to_01315_state() -> uc.ConsumedSourceState:
    consumed_at = "2026-06-01T09:44:51.704139+00:00"
    return pro_target_state(
        consumed_windows=[
            uc.ConsumedWindow(
                source_repo="zenml-io/zenml-cloud-ui",
                previous_tag="0.13.14",
                current_tag="0.13.15",
                consumed_by_release_tag="0.13.15",
                consumed_at=consumed_at,
                pr_keys=[
                    "zenml-io/zenml-cloud-ui#1317",
                    "zenml-io/zenml-cloud-ui#1318",
                ],
                origin="manual-seed-pr75-investigation",
            )
        ],
        consumed_prs={
            "zenml-io/zenml-cloud-ui#1317": uc.ConsumedPR(
                source_repo="zenml-io/zenml-cloud-ui",
                number=1317,
                first_consumed_by_release_tag="0.13.15",
                first_consumed_at=consumed_at,
                previous_tag="0.13.14",
                current_tag="0.13.15",
                origin="manual-seed-pr75-investigation",
            ),
            "zenml-io/zenml-cloud-ui#1318": uc.ConsumedPR(
                source_repo="zenml-io/zenml-cloud-ui",
                number=1318,
                first_consumed_by_release_tag="0.13.15",
                first_consumed_at=consumed_at,
                previous_tag="0.13.14",
                current_tag="0.13.15",
                origin="manual-seed-pr75-investigation",
            ),
        },
    )


def patch_release_window_resolution(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ui_current_tag: str = "0.13.15",
    ui_previous_tag: str = "0.13.14",
) -> list[tuple[str, str | None]]:
    searches: list[tuple[str, str | None]] = []

    def fake_find_latest_release_tag(gh: object, repo_name: str) -> str | None:
        if repo_name == "zenml-io/zenml-cloud-ui":
            return ui_current_tag
        raise AssertionError(f"Unexpected latest-release lookup for {repo_name}")

    def fake_find_previous_tag(gh: object, repo_name: str, current_tag: str) -> str | None:
        if repo_name == "zenml-io/zenml-cloud-api":
            assert current_tag == "0.13.16"
            return "0.13.15"
        if repo_name == "zenml-io/zenml-cloud-ui":
            assert current_tag == ui_current_tag
            return ui_previous_tag
        raise AssertionError(f"Unexpected previous-tag lookup for {repo_name}")

    def fake_get_release_window(
        gh: object,
        repo_name: str,
        since_tag: str | None,
        until_tag: str,
    ) -> tuple[datetime, datetime]:
        return (
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            datetime(2026, 6, 1, tzinfo=timezone.utc),
        )

    def fake_search_merged_prs(
        gh: object,
        repo_name: str,
        base_branch: str,
        since_date: datetime,
        until_date: datetime,
        label: str | None = None,
    ) -> list[dict[str, Any]]:
        searches.append((repo_name, label))
        if repo_name == "zenml-io/zenml-cloud-api":
            return []
        if repo_name == "zenml-io/zenml-cloud-ui" and label == "release-notes":
            return [
                make_pr(1317, "zenml-io/zenml-cloud-ui", ["release-notes"]),
                make_pr(1318, "zenml-io/zenml-cloud-ui", ["release-notes"]),
            ]
        if repo_name == "zenml-io/zenml-cloud-ui" and label == "breaking-change":
            return [make_pr(1319, "zenml-io/zenml-cloud-ui", ["breaking-change"])]
        return []

    monkeypatch.setattr(uc, "find_latest_release_tag", fake_find_latest_release_tag)
    monkeypatch.setattr(uc, "find_previous_tag", fake_find_previous_tag)
    monkeypatch.setattr(uc, "get_release_window", fake_get_release_window)
    monkeypatch.setattr(uc, "search_merged_prs", fake_search_merged_prs)
    return searches


def test_missing_consumed_state_file_returns_empty_state(tmp_path: Path) -> None:
    state = uc.read_consumed_source_state(tmp_path / "missing-state")

    assert state.version == 1
    assert state.targets == {}


def test_empty_consumed_state_file_returns_empty_state(tmp_path: Path) -> None:
    path = tmp_path / "empty-state"
    path.write_text("")

    state = uc.read_consumed_source_state(path)

    assert state.version == 1
    assert state.targets == {}


def test_consumed_state_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = consumed_ui_01314_to_01315_state()

    uc.write_consumed_source_state(state, path)
    loaded = uc.read_consumed_source_state(path)

    target = loaded.targets[
        "zenml-io/zenml-cloud-api::gitbook-release-notes/pro-control-plane.md"
    ]
    assert target.consumed_windows[0].source_repo == "zenml-io/zenml-cloud-ui"
    assert target.consumed_windows[0].previous_tag == "0.13.14"
    assert target.consumed_windows[0].current_tag == "0.13.15"
    assert "zenml-io/zenml-cloud-ui#1317" in target.consumed_prs


def test_committed_seed_is_narrow_and_structured() -> None:
    state = uc.read_consumed_source_state(REPO_ROOT / ".consumed_sources_state")
    target = state.targets[
        "zenml-io/zenml-cloud-api::gitbook-release-notes/pro-control-plane.md"
    ]
    seeded_pr = target.consumed_prs["zenml-io/zenml-cloud-ui#1317"]

    assert state.bootstrap_note
    assert "not a complete historical bootstrap" in state.bootstrap_note
    assert seeded_pr.previous_tag == "0.13.14"
    assert seeded_pr.current_tag == "0.13.15"
    assert seeded_pr.source_window is None


def test_invalid_consumed_state_file_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "invalid-state"
    path.write_text("[not-an-object]")

    with pytest.raises(RuntimeError, match="Invalid JSON"):
        uc.read_consumed_source_state(path)


def test_window_pr_keys_are_reconciled_into_consumed_prs(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        """
        {
          "version": 1,
          "targets": {
            "zenml-io/zenml-cloud-api::gitbook-release-notes/pro-control-plane.md": {
              "trigger_repo": "zenml-io/zenml-cloud-api",
              "markdown_file": "gitbook-release-notes/pro-control-plane.md",
              "consumed_prs": {},
              "consumed_windows": [
                {
                  "source_repo": "zenml-io/zenml-cloud-ui",
                  "previous_tag": "0.13.14",
                  "current_tag": "0.13.15",
                  "consumed_by_release_tag": "0.13.15",
                  "consumed_at": "2026-06-01T09:44:51.704139+00:00",
                  "origin": "manual-test",
                  "pr_keys": [
                    "zenml-io/zenml-cloud-ui#1318",
                    "zenml-io/zenml-cloud-ui#1317",
                    "zenml-io/zenml-cloud-ui#1317"
                  ]
                }
              ]
            }
          }
        }
        """
    )

    state = uc.read_consumed_source_state(path)
    target = state.targets[
        "zenml-io/zenml-cloud-api::gitbook-release-notes/pro-control-plane.md"
    ]

    assert target.consumed_windows[0].pr_keys == [
        "zenml-io/zenml-cloud-ui#1317",
        "zenml-io/zenml-cloud-ui#1318",
    ]
    assert target.consumed_prs["zenml-io/zenml-cloud-ui#1317"].previous_tag == "0.13.14"
    assert target.consumed_prs["zenml-io/zenml-cloud-ui#1317"].current_tag == "0.13.15"
    assert target.consumed_prs["zenml-io/zenml-cloud-ui#1317"].source_window is None
    assert target.consumed_prs["zenml-io/zenml-cloud-ui#1317"].origin == "manual-test"


def test_conflicting_window_and_pr_facts_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        """
        {
          "version": 1,
          "targets": {
            "zenml-io/zenml-cloud-api::gitbook-release-notes/pro-control-plane.md": {
              "trigger_repo": "zenml-io/zenml-cloud-api",
              "markdown_file": "gitbook-release-notes/pro-control-plane.md",
              "consumed_prs": {
                "zenml-io/zenml-cloud-ui#1317": {
                  "source_repo": "zenml-io/zenml-cloud-ui",
                  "number": 1317,
                  "first_consumed_by_release_tag": "0.13.15",
                  "first_consumed_at": "2026-06-01T09:44:51.704139+00:00",
                  "previous_tag": "0.13.13",
                  "current_tag": "0.13.14"
                }
              },
              "consumed_windows": [
                {
                  "source_repo": "zenml-io/zenml-cloud-ui",
                  "previous_tag": "0.13.14",
                  "current_tag": "0.13.15",
                  "consumed_by_release_tag": "0.13.15",
                  "consumed_at": "2026-06-01T09:44:51.704139+00:00",
                  "pr_keys": ["zenml-io/zenml-cloud-ui#1317"]
                }
              ]
            }
          }
        }
        """
    )

    with pytest.raises(RuntimeError, match="window tags conflict"):
        uc.read_consumed_source_state(path)


def test_stale_bundled_ui_window_is_skipped_for_release_notes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    searches = patch_release_window_resolution(monkeypatch)

    collection = uc.collect_multi_source_prs(
        gh=object(),
        trigger_repo="zenml-io/zenml-cloud-api",
        trigger_release_tag="0.13.16",
        consumed_state=consumed_ui_01314_to_01315_state(),
    )

    assert collection.release_notes_prs == []
    assert all(pr["repo"] != "zenml-io/zenml-cloud-ui" for pr in collection.release_notes_prs)
    assert ("zenml-io/zenml-cloud-ui", "release-notes") not in searches
    assert collection.skipped_windows[0].source_repo == "zenml-io/zenml-cloud-ui"
    assert collection.skipped_windows[0].reason == uc.SKIP_REASON_ALREADY_CONSUMED_WINDOW
    assert collection.skipped_windows[0].consumed_by_release_tag == "0.13.15"


def test_stale_bundled_ui_window_is_skipped_for_breaking_prs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    searches = patch_release_window_resolution(monkeypatch)

    collection = uc.collect_multi_source_prs(
        gh=object(),
        trigger_repo="zenml-io/zenml-cloud-api",
        trigger_release_tag="0.13.16",
        consumed_state=consumed_ui_01314_to_01315_state(),
    )

    assert collection.breaking_prs == []
    assert ("zenml-io/zenml-cloud-ui", "breaking-change") not in searches
    assert any(
        skipped.reason == uc.SKIP_REASON_ALREADY_CONSUMED_WINDOW
        for skipped in collection.skipped_windows
    )


def test_consumed_pr_key_is_filtered_even_when_window_is_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_release_window_resolution(
        monkeypatch,
        ui_current_tag="0.13.16",
        ui_previous_tag="0.13.15",
    )
    state = pro_target_state(
        consumed_prs={
            "zenml-io/zenml-cloud-ui#1317": uc.ConsumedPR(
                source_repo="zenml-io/zenml-cloud-ui",
                number=1317,
                first_consumed_by_release_tag="0.13.15",
                first_consumed_at="2026-06-01T09:44:51.704139+00:00",
                previous_tag="0.13.14",
                current_tag="0.13.15",
            )
        }
    )

    collection = uc.collect_multi_source_prs(
        gh=object(),
        trigger_repo="zenml-io/zenml-cloud-api",
        trigger_release_tag="0.13.16",
        consumed_state=state,
    )

    assert [pr["number"] for pr in collection.release_notes_prs] == [1318]
    ui_collection = [
        included
        for included in collection.included_windows
        if included.window.source_repo == "zenml-io/zenml-cloud-ui"
    ][0]
    assert ui_collection.filtered_pr_keys == ["zenml-io/zenml-cloud-ui#1317"]


def test_source_window_report_exposes_included_and_skipped_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_release_window_resolution(monkeypatch)

    collection = uc.collect_multi_source_prs(
        gh=object(),
        trigger_repo="zenml-io/zenml-cloud-api",
        trigger_release_tag="0.13.16",
        consumed_state=consumed_ui_01314_to_01315_state(),
    )

    report = uc.format_source_window_report(collection)

    assert report.startswith(f"{uc.SOURCE_WINDOWS_START_MARKER}\n")
    assert "included zenml-io/zenml-cloud-api 0.13.15 -> 0.13.16" in report
    assert "skipped zenml-io/zenml-cloud-ui 0.13.14 -> 0.13.15" in report
    assert "reason=already_consumed_window" in report
    assert report.endswith(f"\n{uc.SOURCE_WINDOWS_END_MARKER}")

def test_image_state_remains_separate_from_consumed_source_state(tmp_path: Path) -> None:
    image_state_path = tmp_path / ".image_state"
    uc.write_image_state(
        uc.ImageState(
            last_image_number=12,
            last_release_tag="0.13.15",
            last_markdown_file="gitbook-release-notes/pro-control-plane.md",
            updated_at="2026-06-01T09:44:51.704139+00:00",
        ),
        image_state_path,
    )

    loaded = uc.read_image_state(image_state_path)
    payload = uc._model_dump(loaded)

    assert uc.IMAGE_STATE_FILE.name == ".image_state"
    assert uc.CONSUMED_SOURCE_STATE_FILE.name == ".consumed_sources_state"
    assert set(payload) == {
        "last_image_number",
        "last_release_tag",
        "last_markdown_file",
        "updated_at",
    }
