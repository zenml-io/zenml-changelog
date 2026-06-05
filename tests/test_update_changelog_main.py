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


class FakeOpenAIForShadow:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.responses = self

    def parse(self, **kwargs: Any) -> Any:
        output_model = kwargs["text_format"]
        if output_model is uc.GroupedChangelogOutput:
            return type(
                "Response",
                (),
                {
                    "output_parsed": uc.GroupedChangelogOutput(
                        entries=[
                            uc.GroupedChangelogEntry(
                                title="Shadow grouped entry",
                                description="Shadow grouped entry description",
                                suggested_labels=[uc.ChangelogLabel.IMPROVEMENT],
                                pr_numbers=[1],
                            )
                        ]
                    ),
                    "status": "completed",
                    "output": [],
                    "incomplete_details": None,
                },
            )()
        if output_model is uc.BreakingChangesOutput:
            return type(
                "Response",
                (),
                {
                    "output_parsed": uc.BreakingChangesOutput(
                        bullets=[
                            "Update configuration as described in [PR #2](https://github.com/zenml-io/zenml/pull/2)"
                        ]
                    ),
                    "status": "completed",
                    "output": [],
                    "incomplete_details": None,
                },
            )()
        if output_model is uc.MarkdownSection:
            return type(
                "Response",
                (),
                {
                    "output_parsed": uc.MarkdownSection(
                        content="#### Improved\n\nUsers can compare output from [PR #1](https://github.com/zenml-io/zenml/pull/1)."
                    ),
                    "status": "completed",
                    "output": [],
                    "incomplete_details": None,
                },
            )()
        raise AssertionError(f"Unexpected output model: {output_model}")


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


def test_main_no_changes_does_not_require_llm_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result_path = configure_common_main_stubs(monkeypatch, tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        uc,
        "collect_multi_source_prs",
        lambda **kwargs: uc.MultiSourceCollectionResult(),
    )

    def fail_if_llm_client_is_built() -> uc.StructuredLLMClient:
        raise AssertionError("No-changes path must not initialize an LLM client")

    monkeypatch.setattr(uc, "build_structured_llm_client_from_env", fail_if_llm_client_is_built)

    with pytest.raises(SystemExit) as exit_info:
        uc.main()

    assert exit_info.value.code == 0
    result = wr.read_changelog_workflow_result(result_path)
    assert result.has_changes is False


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
                "slug": "grouped-release-note",
                "title": "Grouped release note",
                "description": "Grouped release note description",
                "published_at": "2026-06-02T10:00:00Z",
                "published": True,
                "audience": "oss",
                "labels": ["improvement"],
                "feature_image_url": "",
                "video_url": "",
                "learn_more_url": uc.PLACEHOLDER_LEARN_MORE_URL,
                "docs_url": uc.PLACEHOLDER_DOCS_URL,
                "should_highlight": False,
            }
        ],
    )
    monkeypatch.setattr(uc, "validate_changelog_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(uc, "validate_changelog", lambda *args, **kwargs: None)
    monkeypatch.setattr(uc, "get_next_image_number", lambda **kwargs: 3)
    monkeypatch.setattr(uc, "llm_generate_release_notes_body", lambda *args, **kwargs: "BODY")
    monkeypatch.setattr(uc, "render_release_notes_section", lambda *args, **kwargs: "RELEASE NOTES\n")
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


def test_main_validates_release_note_body_before_writing_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result_path = configure_common_main_stubs(monkeypatch, tmp_path)
    release_pr = make_pr(1, body="This PR has enough body text to avoid manual-review noise.")
    collection = make_collection(release_notes_prs=[release_pr], breaking_prs=[])
    changelog_path = tmp_path / "changelog.json"
    changelog_path.write_text("[]\n", encoding="utf-8")

    monkeypatch.setattr(uc, "collect_multi_source_prs", lambda **kwargs: collection)
    monkeypatch.setattr(
        uc,
        "generate_valid_grouped_changelog_entries",
        lambda **kwargs: [
            {
                "id": kwargs["starting_id"],
                "title": "Grouped release note",
                "description": "Grouped release note description",
                "published_at": "2026-06-02T10:00:00Z",
                "published": True,
                "audience": "oss",
                "labels": ["improvement"],
                "feature_image_url": "",
                "video_url": "",
                "learn_more_url": uc.PLACEHOLDER_LEARN_MORE_URL,
                "docs_url": uc.PLACEHOLDER_DOCS_URL,
                "should_highlight": False,
            }
        ],
    )

    def fail_release_note_body(*args: Any, **kwargs: Any) -> str:
        raise uc.LLMOutputValidationError(["bad release-note body"])

    def fail_if_called(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("production artifact writer should not be called")

    monkeypatch.setattr(uc, "llm_generate_release_notes_body", fail_release_note_body)
    monkeypatch.setattr(uc, "validate_changelog", fail_if_called)
    monkeypatch.setattr(uc, "get_next_image_number", fail_if_called)
    monkeypatch.setattr(uc, "update_markdown_file", fail_if_called)
    monkeypatch.setattr(uc, "write_consumed_source_state", fail_if_called)
    monkeypatch.setattr(uc, "write_changelog_workflow_result", fail_if_called)

    with pytest.raises(uc.LLMOutputValidationError, match="bad release-note body"):
        uc.main()

    assert changelog_path.read_text(encoding="utf-8") == "[]\n"
    assert not (tmp_path / ".image_state").exists()
    assert not (tmp_path / ".consumed_sources_state").exists()
    assert not result_path.exists()


def test_main_validates_changelog_schema_before_replacing_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result_path = configure_common_main_stubs(monkeypatch, tmp_path)
    release_pr = make_pr(1, body="This PR has enough body text to avoid manual-review noise.")
    collection = make_collection(release_notes_prs=[release_pr], breaking_prs=[])
    changelog_path = tmp_path / "changelog.json"
    changelog_path.write_text("[]\n", encoding="utf-8")

    monkeypatch.setattr(uc, "collect_multi_source_prs", lambda **kwargs: collection)
    monkeypatch.setattr(uc, "llm_generate_breaking_changes_bullets", lambda **kwargs: [])
    monkeypatch.setattr(uc, "llm_generate_release_notes_body", lambda *args, **kwargs: "BODY")
    monkeypatch.setattr(
        uc,
        "generate_valid_grouped_changelog_entries",
        lambda **kwargs: [
            {
                "id": kwargs["starting_id"],
                "slug": "bad-entry",
                "title": "Bad entry",
                "description": "This entry has an extra field and must fail schema validation.",
                "published_at": "2026-06-02T10:00:00Z",
                "unexpected": "not allowed",
            }
        ],
    )

    def fail_if_called(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("production artifact writer should not be called after schema failure")

    monkeypatch.setattr(uc, "get_next_image_number", fail_if_called)
    monkeypatch.setattr(uc, "update_markdown_file", fail_if_called)
    monkeypatch.setattr(uc, "write_consumed_source_state", fail_if_called)
    monkeypatch.setattr(uc, "write_changelog_workflow_result", fail_if_called)

    with pytest.raises(Exception, match="Additional properties are not allowed|unexpected"):
        uc.main()

    assert changelog_path.read_text(encoding="utf-8") == "[]\n"
    assert not (tmp_path / ".image_state").exists()
    assert not (tmp_path / ".consumed_sources_state").exists()
    assert not result_path.exists()


def test_blank_private_repo_token_falls_back_to_github_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_common_main_stubs(monkeypatch, tmp_path)
    created: dict[str, object] = {}

    class CapturingGithub:
        def __init__(self, auth: object) -> None:
            created["auth"] = auth

    monkeypatch.setenv("PRIVATE_REPO_TOKEN", "   ")
    monkeypatch.setattr(uc.Auth, "Token", lambda token: f"auth:{token}")
    monkeypatch.setattr(uc, "Github", CapturingGithub)
    monkeypatch.setattr(uc, "collect_multi_source_prs", lambda **kwargs: uc.MultiSourceCollectionResult())

    with pytest.raises(SystemExit):
        uc.main()

    assert created["auth"] == "auth:token"


def test_openai_shadow_comments_write_labeled_review_files_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(uc.OPENAI_SHADOW_MODE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setattr(uc, "OpenAI", FakeOpenAIForShadow)

    uc.write_openai_shadow_comments(
        grouping_prs=[make_pr(1, body="This PR has enough detail for output.")],
        body_prs=[make_pr(1, body="This PR has enough detail for output.")],
        breaking_prs=[make_pr(2, body="This breaking PR has enough detail for output.")],
        source_repo="zenml-io/zenml",
        published_at="2026-06-02T10:00:00Z",
        starting_id=10,
        include_pr_links=True,
    )

    widget_comment = (tmp_path / uc.DEFAULT_OPENAI_SHADOW_WIDGET_COMMENT).read_text(encoding="utf-8")
    release_notes_comment = (tmp_path / uc.DEFAULT_OPENAI_SHADOW_RELEASE_NOTES_COMMENT).read_text(encoding="utf-8")

    assert uc.OPENAI_SHADOW_WIDGET_MARKER in widget_comment
    assert "### Output type: `dashboard grouped changelog entries`" in widget_comment
    assert "- Provider: `openai`" in widget_comment
    assert "- Model: `gpt-5.4`" in widget_comment
    assert "- Status: `passed`" in widget_comment
    assert "Shadow grouped entry" in widget_comment
    assert "schema_entries" in widget_comment

    assert uc.OPENAI_SHADOW_RELEASE_NOTES_MARKER in release_notes_comment
    assert "### Output type: `breaking_changes`" in release_notes_comment
    assert "### Output type: `release_notes_body`" in release_notes_comment
    assert release_notes_comment.count("- Provider: `openai`") == 2
    assert release_notes_comment.count("- Model: `gpt-5.4`") == 1
    assert release_notes_comment.count("- Model: `gpt-5.5`") == 1
    assert "Users can compare output" in release_notes_comment

    assert not (tmp_path / "changelog.json").exists()
    assert not (tmp_path / "gitbook-release-notes").exists()
    assert not (tmp_path / ".image_state").exists()
    assert not (tmp_path / ".consumed_sources_state").exists()


def test_openai_shadow_mode_skips_without_openai_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(uc.OPENAI_SHADOW_MODE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", "   ")

    uc.write_openai_shadow_comments(
        grouping_prs=[make_pr(1)],
        body_prs=[make_pr(1)],
        breaking_prs=[],
        source_repo="zenml-io/zenml",
        published_at="2026-06-02T10:00:00Z",
        starting_id=1,
        include_pr_links=True,
    )

    assert not (tmp_path / uc.DEFAULT_OPENAI_SHADOW_WIDGET_COMMENT).exists()
    assert not (tmp_path / uc.DEFAULT_OPENAI_SHADOW_RELEASE_NOTES_COMMENT).exists()


def test_openai_shadow_mode_rejects_production_artifact_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    changelog_path = tmp_path / "changelog.json"
    changelog_path.write_text("original changelog\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(uc.OPENAI_SHADOW_MODE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setenv(uc.OPENAI_SHADOW_WIDGET_COMMENT_ENV, "changelog.json")
    monkeypatch.setattr(uc, "OpenAI", FakeOpenAIForShadow)

    uc.write_openai_shadow_comments(
        grouping_prs=[make_pr(1)],
        body_prs=[make_pr(1)],
        breaking_prs=[],
        source_repo="zenml-io/zenml",
        published_at="2026-06-02T10:00:00Z",
        starting_id=1,
        include_pr_links=True,
    )

    assert changelog_path.read_text(encoding="utf-8") == "original changelog\n"
    assert not (tmp_path / uc.DEFAULT_OPENAI_SHADOW_RELEASE_NOTES_COMMENT).exists()


def test_openai_shadow_failure_writes_failure_comment_without_raising(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FailingOpenAIForShadow:
        def __init__(self, **kwargs: Any) -> None:
            self.responses = self

        def parse(self, **kwargs: Any) -> Any:
            raise RuntimeError("shadow provider unavailable")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(uc.OPENAI_SHADOW_MODE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setattr(uc, "OpenAI", FailingOpenAIForShadow)

    uc.write_openai_shadow_comments(
        grouping_prs=[make_pr(1)],
        body_prs=[make_pr(1)],
        breaking_prs=[],
        source_repo="zenml-io/zenml",
        published_at="2026-06-02T10:00:00Z",
        starting_id=1,
        include_pr_links=True,
    )

    widget_comment = (tmp_path / uc.DEFAULT_OPENAI_SHADOW_WIDGET_COMMENT).read_text(encoding="utf-8")
    release_notes_comment = (tmp_path / uc.DEFAULT_OPENAI_SHADOW_RELEASE_NOTES_COMMENT).read_text(encoding="utf-8")

    assert "- Model: `gpt-5.4`" in widget_comment
    assert "- Status: `failed`" in widget_comment
    assert "shadow provider unavailable" in widget_comment
    assert "### Output type: `breaking_changes`" in release_notes_comment
    assert "- Model: `gpt-5.4`" in release_notes_comment
    assert "- Status: `passed`" in release_notes_comment
    assert "### Output type: `release_notes_body`" in release_notes_comment
    assert "- Model: `gpt-5.5`" in release_notes_comment
    assert "- Status: `failed`" in release_notes_comment
