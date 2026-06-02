from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import source_windows as sw
from scripts import update_changelog as uc
from scripts import workflow_result as wr


class FakeAnthropic:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key


class FakeGithub:
    def __init__(self, auth: object) -> None:
        self.auth = auth


def make_pr(number: int, body: str = "short") -> dict[str, Any]:
    return {
        "number": number,
        "title": f"PR {number}",
        "labels": ["release-notes"],
        "url": f"https://github.com/zenml-io/zenml/pull/{number}",
        "body": body,
        "repo": "zenml-io/zenml",
    }


def make_collection(
    *,
    release_notes_prs: list[dict[str, Any]],
    breaking_prs: list[dict[str, Any]],
) -> uc.MultiSourceCollectionResult:
    window = sw.SourceReleaseWindow(
        source_repo="zenml-io/zenml",
        base_branch="develop",
        previous_tag="0.84.0",
        current_tag="0.85.0",
        since_date=uc.datetime(2026, 6, 1, tzinfo=uc.timezone.utc),
        until_date=uc.datetime(2026, 6, 2, tzinfo=uc.timezone.utc),
        is_primary=True,
    )
    return uc.MultiSourceCollectionResult(
        included_windows=[
            sw.SourceWindowCollection(
                window=window,
                release_notes_prs=release_notes_prs,
                breaking_prs=breaking_prs,
            )
        ],
        release_notes_prs=release_notes_prs,
        breaking_prs=breaking_prs,
    )


def configure_common_main_stubs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    result_path = tmp_path / "workflow-result.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOURCE_REPO", "zenml-io/zenml")
    monkeypatch.setenv("RELEASE_TAG", "0.85.0")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-token")
    monkeypatch.setenv("RELEASE_URL", "https://github.com/zenml-io/zenml/releases/tag/0.85.0")
    monkeypatch.setenv("PUBLISHED_AT", "2026-06-02T10:00:00Z")
    monkeypatch.setenv(wr.CHANGELOG_WORKFLOW_RESULT_ENV, str(result_path))
    monkeypatch.setattr(uc, "Anthropic", FakeAnthropic)
    monkeypatch.setattr(uc, "Github", FakeGithub)
    monkeypatch.setattr(uc, "find_previous_tag", lambda *args: "0.84.0")
    monkeypatch.setattr(uc, "read_consumed_source_state", lambda: uc.ConsumedSourceState())
    return result_path


def test_main_no_changes_writes_structured_result_and_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result_path = configure_common_main_stubs(monkeypatch, tmp_path)
    monkeypatch.setattr(
        uc,
        "collect_multi_source_prs",
        lambda **kwargs: uc.MultiSourceCollectionResult(),
    )

    with pytest.raises(SystemExit) as exit_info:
        uc.main()

    assert exit_info.value.code == 0
    result = wr.read_changelog_workflow_result(result_path)
    assert result.has_changes is False
    assert result.markdown_file == "gitbook-release-notes/server-sdk.md"
    assert result.breaking_changes == ""
    assert result.needs_attention == ""
    assert result.source_windows == ""


def test_main_happy_path_writes_structured_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result_path = configure_common_main_stubs(monkeypatch, tmp_path)
    release_pr = make_pr(1, body="short")
    breaking_pr = make_pr(2, body="This breaking PR has enough body text to avoid manual-review noise.")
    collection = make_collection(
        release_notes_prs=[release_pr],
        breaking_prs=[breaking_pr],
    )
    (tmp_path / "changelog.json").write_text("[]\n", encoding="utf-8")
    monkeypatch.setattr(uc, "collect_multi_source_prs", lambda **kwargs: collection)
    monkeypatch.setattr(
        uc,
        "llm_generate_breaking_changes_bullets",
        lambda **kwargs: ["Breaking API changed"],
    )
    monkeypatch.setattr(
        uc,
        "generate_valid_grouped_changelog_entries",
        lambda **kwargs: [
            {
                "id": kwargs["starting_id"],
                "title": "Grouped release note",
                "description": "Grouped release note description",
                "label": "improvement",
                "source_prs": [1],
                "source_repo": "zenml-io/zenml",
                "published_at": "2026-06-02T10:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(uc, "validate_changelog", lambda *args, **kwargs: None)
    monkeypatch.setattr(uc, "get_next_image_number", lambda **kwargs: 3)
    monkeypatch.setattr(uc, "render_release_header", lambda *args, **kwargs: "HEADER\n")
    monkeypatch.setattr(uc, "render_breaking_section", lambda *args, **kwargs: "BREAKING\n")
    monkeypatch.setattr(uc, "llm_generate_release_notes_body", lambda *args, **kwargs: "BODY")
    monkeypatch.setattr(uc, "render_release_footer", lambda *args, **kwargs: "FOOTER")
    monkeypatch.setattr(uc, "update_markdown_file", lambda *args, **kwargs: None)
    monkeypatch.setattr(uc, "mark_consumed_after_success", lambda **kwargs: kwargs["state"])
    monkeypatch.setattr(uc, "write_consumed_source_state", lambda *args, **kwargs: None)

    uc.main()

    result = wr.read_changelog_workflow_result(result_path)
    assert result.has_changes is True
    assert result.markdown_file == "gitbook-release-notes/server-sdk.md"
    assert result.breaking_changes == "- Breaking API changed"
    assert result.needs_attention == (
        f"{wr.NEEDS_ATTENTION_HEADER}\n"
        "- PR #1: PR 1 (https://github.com/zenml-io/zenml/pull/1)"
    )
    assert "included zenml-io/zenml 0.84.0 -> 0.85.0" in result.source_windows
    assert "release_notes=1" in result.source_windows
    assert "breaking=1" in result.source_windows
