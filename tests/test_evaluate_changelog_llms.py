from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import changelog_rendering as rendering
from scripts import evaluate_changelog_llms as evaluator
from scripts import update_changelog as uc


FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "changelog-evals"


def run_static_eval(
    tmp_path: Path,
    *,
    fixture_ids: set[str] | None = None,
    candidate_filter: set[str] | None = None,
) -> evaluator.RunSummary:
    return evaluator.run_eval(
        fixtures_dir=FIXTURES_DIR,
        output_root=tmp_path / "eval-results",
        run_id="test-run",
        fixture_ids=fixture_ids,
        candidate_filter=candidate_filter,
        live_candidates=[],
    )


def test_loads_synthetic_fixture_set() -> None:
    fixtures = evaluator.load_fixtures(FIXTURES_DIR)

    fixture_ids = {fixture.fixture_id for fixture in fixtures}

    assert {
        "synthetic-oss-small",
        "synthetic-pro-no-links",
        "synthetic-oss-breaking",
        "synthetic-no-changes",
        "synthetic-ambiguous-pr-numbers",
        "synthetic-bad-grouping",
    }.issubset(fixture_ids)
    assert all(fixture.offline_candidates for fixture in fixtures)


def test_no_changes_fixture_makes_no_provider_calls(tmp_path: Path) -> None:
    summary = run_static_eval(tmp_path, fixture_ids={"synthetic-no-changes"})

    result = summary.results[0]

    assert result.hard_gate_status == "pass"
    assert result.provider_call_count == 0
    assert (Path(summary.run_dir) / "summary.md").exists()
    assert (Path(summary.run_dir) / "comparison.html").exists()


def test_valid_fake_outputs_pass_hard_gates_and_write_reports(tmp_path: Path) -> None:
    summary = run_static_eval(
        tmp_path,
        fixture_ids={
            "synthetic-oss-small",
            "synthetic-pro-no-links",
            "synthetic-oss-breaking",
        },
    )

    assert summary.unexpected_count == 0
    assert all(result.hard_gate_status == "pass" for result in summary.results)

    changed_results = [
        result
        for result in summary.results
        if result.fixture_id != "synthetic-no-changes"
    ]
    for result in changed_results:
        run_dir = Path(summary.run_dir)
        assert (run_dir / result.fixture_id / result.candidate_id / "report.json").exists()
        assert (run_dir / result.fixture_id / result.candidate_id / "candidate-changelog.json").exists()
        assert (run_dir / result.fixture_id / result.candidate_id / "candidate-release-notes.md").exists()


def test_invalid_grouping_fails_hard_gate(tmp_path: Path) -> None:
    summary = run_static_eval(tmp_path, fixture_ids={"synthetic-bad-grouping"})

    result = summary.results[0]

    assert result.hard_gate_status == "fail"
    assert result.matched_expectation is True
    assert any(
        "appears in more than one grouped changelog entry" in error
        or "not assigned to any grouped changelog entry" in error
        for error in result.errors
    )
    assert not (Path(summary.run_dir) / result.fixture_id / result.candidate_id / "candidate-release-notes.md").exists()


def test_ambiguous_pr_numbers_fail_before_provider_call(tmp_path: Path) -> None:
    summary = run_static_eval(tmp_path, fixture_ids={"synthetic-ambiguous-pr-numbers"})

    result = summary.results[0]

    assert result.hard_gate_status == "fail"
    assert result.matched_expectation is True
    assert result.provider_call_count == 0
    assert any("multiple source PRs share the same PR number" in error for error in result.errors)


def test_eval_never_calls_production_write_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("production write path was called")

    for name in [
        "main",
        "update_markdown_file",
        "write_image_state",
        "get_next_image_number",
        "write_consumed_source_state",
        "mark_consumed_after_success",
        "write_changelog_workflow_result",
    ]:
        monkeypatch.setattr(uc, name, forbidden)
    monkeypatch.setattr(rendering, "update_markdown_file", forbidden)

    summary = run_static_eval(tmp_path, fixture_ids={"synthetic-oss-small"})
    run_dir = Path(summary.run_dir).resolve()

    for result in summary.results:
        for relative_path in result.written_files:
            written_path = (run_dir / relative_path).resolve()
            assert written_path.is_relative_to(run_dir)
            assert written_path not in evaluator.PRODUCTION_ARTIFACTS


def test_run_eval_rejects_repo_root_output_directory() -> None:
    with pytest.raises(evaluator.EvalHarnessError, match="repository root"):
        evaluator.run_eval(
            fixtures_dir=FIXTURES_DIR,
            output_root=REPO_ROOT,
            run_id=".",
            fixture_ids={"synthetic-no-changes"},
            candidate_filter=None,
            live_candidates=[],
        )


def test_capture_fixture_rejects_protected_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protected = (tmp_path / "changelog.json").resolve()
    monkeypatch.setattr(evaluator, "PRODUCTION_ARTIFACTS", {protected})

    with pytest.raises(evaluator.EvalHarnessError, match="production artifact"):
        evaluator.capture_fixture(
            input_path=FIXTURES_DIR / "synthetic-no-changes.json",
            output_path=protected,
        )

    assert not protected.exists()


def test_live_no_changes_fixture_does_not_require_api_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    live_candidate = evaluator.LiveCandidate(
        candidate_id="live-openai-gpt-5-4-mini",
        provider="openai",
        model="gpt-5.4-mini",
        display_name="Live OpenAI mini",
    )

    summary = evaluator.run_eval(
        fixtures_dir=FIXTURES_DIR,
        output_root=tmp_path / "eval-results",
        run_id="test-run",
        fixture_ids={"synthetic-no-changes"},
        candidate_filter={live_candidate.candidate_id},
        live_candidates=[live_candidate],
        allow_live_provider_calls=True,
    )

    result = summary.results[0]
    assert result.hard_gate_status == "pass"
    assert result.provider_call_count == 0


def test_comparison_html_is_labeled_with_provider_and_model(tmp_path: Path) -> None:
    summary = run_static_eval(tmp_path, fixture_ids={"synthetic-oss-small"})

    html = (Path(summary.run_dir) / "comparison.html").read_text()

    assert "Fake Claude baseline" in html
    assert "Fake OpenAI mini" in html
    assert "anthropic / claude-sonnet-4-5-20250929" in html
    assert "openai / gpt-5.4-mini" in html
    assert "Provider and model labels are intentionally visible" in html


def test_gitignore_excludes_eval_results() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text()

    assert "eval-results/" in gitignore


def test_run_eval_rejects_live_candidates_without_explicit_allow_flag(tmp_path: Path) -> None:
    live_candidate = evaluator.LiveCandidate(
        candidate_id="live-openai-gpt-5-4-mini",
        provider="openai",
        model="gpt-5.4-mini",
        display_name="Live OpenAI mini",
    )

    with pytest.raises(evaluator.EvalHarnessError, match="allow_live_provider_calls=True"):
        evaluator.run_eval(
            fixtures_dir=FIXTURES_DIR,
            output_root=tmp_path / "eval-results",
            run_id="test-run",
            fixture_ids={"synthetic-no-changes"},
            candidate_filter={live_candidate.candidate_id},
            live_candidates=[live_candidate],
        )


def test_parse_live_candidate_rejects_empty_provider() -> None:
    with pytest.raises(Exception, match="Live provider"):
        evaluator.parse_live_candidate(":gpt-5.4-mini:OpenAI mini")


def test_live_candidates_require_explicit_allow_flag_in_cli() -> None:
    exit_code = evaluator.main(
        [
            "run-eval",
            "--fixtures-dir",
            str(FIXTURES_DIR),
            "--live-candidate",
            "openai:gpt-5.4-mini:OpenAI mini",
        ]
    )

    assert exit_code == 2
