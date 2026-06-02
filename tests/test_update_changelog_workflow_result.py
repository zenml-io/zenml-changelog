from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import workflow_result as wr


def make_result(**overrides: object) -> wr.ChangelogWorkflowResult:
    payload = {
        "has_changes": True,
        "markdown_file": "gitbook-release-notes/server-sdk.md",
        "breaking_changes": "- Removed old behavior",
        "needs_attention": "",
        "source_windows": "included zenml-io/zenml 0.84.0 -> 0.85.0 release_notes=2 breaking=1 filtered=0",
    }
    payload.update(overrides)
    return wr.ChangelogWorkflowResult(**payload)


def test_workflow_result_accepts_valid_changes_result() -> None:
    result = make_result()

    assert result.has_changes is True
    assert result.markdown_file == "gitbook-release-notes/server-sdk.md"


def test_workflow_result_is_frozen() -> None:
    result = make_result()

    with pytest.raises(wr.ValidationError, match="frozen"):
        result.markdown_file = "gitbook-release-notes/pro-control-plane.md"


@pytest.mark.parametrize("field", ["markdown_file", "source_windows"])
def test_changes_result_requires_artifact_fields(field: str) -> None:
    with pytest.raises(wr.ValidationError, match=field):
        make_result(**{field: ""})


def test_no_changes_result_allows_empty_artifact_fields() -> None:
    result = wr.ChangelogWorkflowResult(
        has_changes=False,
        markdown_file="",
        breaking_changes="",
        needs_attention="",
        source_windows="",
    )

    assert result.has_changes is False


@pytest.mark.parametrize("value", ["true", "false"])
def test_workflow_result_rejects_string_booleans(value: str) -> None:
    with pytest.raises(wr.ValidationError):
        make_result(has_changes=value)


@pytest.mark.parametrize(
    "markdown_file",
    [
        "gitbook-release-notes/unknown.md",
        "gitbook-release-notes/server-sdk.md\nother=value",
    ],
)
def test_workflow_result_rejects_invalid_non_empty_markdown_file(markdown_file: str) -> None:
    with pytest.raises(wr.ValidationError, match="markdown_file"):
        make_result(markdown_file=markdown_file)


def test_workflow_result_json_round_trip_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    result = make_result(needs_attention="Needs review")

    wr.write_changelog_workflow_result(result, path)

    assert path.read_text(encoding="utf-8") == (
        "{\n"
        '  "breaking_changes": "- Removed old behavior",\n'
        '  "has_changes": true,\n'
        '  "markdown_file": "gitbook-release-notes/server-sdk.md",\n'
        '  "needs_attention": "Needs review",\n'
        '  "source_windows": "included zenml-io/zenml 0.84.0 -> 0.85.0 release_notes=2 breaking=1 filtered=0"\n'
        "}\n"
    )
    loaded = wr.read_changelog_workflow_result(path)
    assert loaded == result


def test_read_workflow_result_fails_closed_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="not found"):
        wr.read_changelog_workflow_result(tmp_path / "missing.json")


def test_read_workflow_result_fails_closed_for_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    path.write_text("[not-json]", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Invalid changelog workflow result JSON"):
        wr.read_changelog_workflow_result(path)


def test_read_workflow_result_fails_closed_for_invalid_payload(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    path.write_text('{"has_changes": "true"}\n', encoding="utf-8")

    with pytest.raises(RuntimeError, match="Invalid changelog workflow result"):
        wr.read_changelog_workflow_result(path)


def test_format_breaking_changes_output_preserves_bullets_only_contract() -> None:
    assert wr.format_breaking_changes_output(
        ["First change", "", " Second change "],
        is_major_bump=False,
    ) == "- First change\n- Second change"


def test_format_breaking_changes_output_major_bump_fallback_is_exact() -> None:
    assert wr.format_breaking_changes_output([], is_major_bump=True) == (
        "- Major version bump detected; manual review recommended"
    )


def test_format_breaking_changes_output_empty_for_non_major_without_bullets() -> None:
    assert wr.format_breaking_changes_output([], is_major_bump=False) == ""


def test_format_needs_attention_output_is_header_plus_pr_bullets() -> None:
    output = wr.format_needs_attention_output(
        [
            {
                "number": "123",
                "title": "Needs a better description",
                "url": "https://github.com/zenml-io/zenml/pull/123",
            }
        ]
    )

    assert output == (
        f"{wr.NEEDS_ATTENTION_HEADER}\n"
        "- PR #123: Needs a better description (https://github.com/zenml-io/zenml/pull/123)"
    )


def test_format_needs_attention_output_empty_when_no_prs() -> None:
    assert wr.format_needs_attention_output([]) == ""


def test_format_needs_attention_output_renders_empty_url_as_plain_note() -> None:
    output = wr.format_needs_attention_output(
        [
            {
                "number": "N/A",
                "title": "No release-notes PRs found; changelog derived from breaking PRs only",
                "url": "",
            }
        ]
    )

    assert output == (
        f"{wr.NEEDS_ATTENTION_HEADER}\n"
        "- No release-notes PRs found; changelog derived from breaking PRs only"
    )


def test_github_output_writer_writes_all_stable_output_names(tmp_path: Path) -> None:
    path = tmp_path / "github-output.txt"
    result = make_result(
        breaking_changes="- Breaking one\n- Breaking two",
        needs_attention=f"{wr.NEEDS_ATTENTION_HEADER}\n- PR #123: Needs review (https://example.test/pr/123)",
    )

    wr.write_changelog_github_outputs(result, path)

    output = path.read_text(encoding="utf-8")
    assert output == (
        "has_changes=true\n"
        "markdown_file<<ZENML_CHANGELOG_OUTPUT_MARKDOWN_FILE\n"
        "gitbook-release-notes/server-sdk.md\n"
        "ZENML_CHANGELOG_OUTPUT_MARKDOWN_FILE\n"
        "breaking_changes<<ZENML_CHANGELOG_OUTPUT_BREAKING_CHANGES\n"
        "- Breaking one\n"
        "- Breaking two\n"
        "ZENML_CHANGELOG_OUTPUT_BREAKING_CHANGES\n"
        "needs_attention<<ZENML_CHANGELOG_OUTPUT_NEEDS_ATTENTION\n"
        f"{wr.NEEDS_ATTENTION_HEADER}\n"
        "- PR #123: Needs review (https://example.test/pr/123)\n"
        "ZENML_CHANGELOG_OUTPUT_NEEDS_ATTENTION\n"
        "source_windows<<ZENML_CHANGELOG_OUTPUT_SOURCE_WINDOWS\n"
        "included zenml-io/zenml 0.84.0 -> 0.85.0 release_notes=2 breaking=1 filtered=0\n"
        "ZENML_CHANGELOG_OUTPUT_SOURCE_WINDOWS\n"
    )


def test_github_output_writer_handles_empty_multiline_values(tmp_path: Path) -> None:
    path = tmp_path / "github-output.txt"
    result = wr.ChangelogWorkflowResult(
        has_changes=False,
        markdown_file="",
        breaking_changes="",
        needs_attention="",
        source_windows="",
    )

    wr.write_changelog_github_outputs(result, path)

    output = path.read_text(encoding="utf-8")
    assert "has_changes=false\n" in output
    assert "breaking_changes<<ZENML_CHANGELOG_OUTPUT_BREAKING_CHANGES\nZENML_CHANGELOG_OUTPUT_BREAKING_CHANGES\n" in output


def test_github_output_writer_avoids_delimiter_line_collision(tmp_path: Path) -> None:
    path = tmp_path / "github-output.txt"
    result = make_result(
        source_windows=(
            "included zenml-io/zenml 0.84.0 -> 0.85.0 release_notes=2 breaking=1 filtered=0\n"
            "ZENML_CHANGELOG_OUTPUT_SOURCE_WINDOWS"
        )
    )

    wr.write_changelog_github_outputs(result, path)

    output = path.read_text(encoding="utf-8")
    assert "source_windows<<ZENML_CHANGELOG_OUTPUT_SOURCE_WINDOWS_1\n" in output
    assert output.endswith("ZENML_CHANGELOG_OUTPUT_SOURCE_WINDOWS_1\n")


def test_write_github_outputs_mode_reads_result_and_requires_output_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "result.json"
    output_path = tmp_path / "github-output.txt"
    wr.write_changelog_workflow_result(make_result(), result_path)
    monkeypatch.setenv(wr.CHANGELOG_WORKFLOW_RESULT_ENV, str(result_path))
    monkeypatch.setenv(wr.GITHUB_OUTPUT_ENV, str(output_path))

    wr.run_write_github_outputs_mode()

    output = output_path.read_text(encoding="utf-8")
    assert "has_changes=true\n" in output


def test_write_github_outputs_mode_fails_without_output_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "result.json"
    wr.write_changelog_workflow_result(make_result(), result_path)
    monkeypatch.setenv(wr.CHANGELOG_WORKFLOW_RESULT_ENV, str(result_path))
    monkeypatch.delenv(wr.GITHUB_OUTPUT_ENV, raising=False)

    with pytest.raises(RuntimeError, match=wr.GITHUB_OUTPUT_ENV):
        wr.run_write_github_outputs_mode()


def test_cli_dispatches_write_github_outputs_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "result.json"
    output_path = tmp_path / "github-output.txt"
    wr.write_changelog_workflow_result(make_result(), result_path)
    monkeypatch.setenv(wr.CHANGELOG_WORKFLOW_RESULT_ENV, str(result_path))
    monkeypatch.setenv(wr.GITHUB_OUTPUT_ENV, str(output_path))

    wr.cli(["write-github-outputs"])

    output = output_path.read_text(encoding="utf-8")
    assert "source_windows<<ZENML_CHANGELOG_OUTPUT_SOURCE_WINDOWS\n" in output


def test_cli_rejects_unknown_args() -> None:
    with pytest.raises(SystemExit, match="Usage: workflow_result.py"):
        wr.cli(["unknown"])
