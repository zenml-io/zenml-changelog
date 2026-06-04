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
"""Offline-first changelog LLM evaluation harness.

This script is intentionally non-production. It reads static fixtures, runs
candidate model outputs through the same hard validators used by the release
automation, and writes reports only under an evaluation output directory.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Sequence, TypeVar

from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import changelog_artifact_safety as artifact_safety
from scripts import changelog_config as cfg
from scripts import changelog_entry_builder as entry_builder
from scripts import changelog_env as env
from scripts import changelog_llm_generation as generation
from scripts import changelog_llm_providers as providers
from scripts import changelog_rendering as rendering
from scripts import changelog_schema_validation as schema_validation
from scripts import changelog_validators as validators
from scripts.changelog_llm_outputs import (
    LLM_CALL_BREAKING_CHANGES,
    LLM_CALL_GROUPED_CHANGELOG_ENTRIES,
    LLM_CALL_RELEASE_NOTES_BODY,
    GroupedChangelogOutput,
)

DEFAULT_FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "changelog-evals"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "eval-results" / "openai-migration"
SCHEMA_PATH = REPO_ROOT / "changelog_schema" / "announcement-schema.json"
PRODUCTION_ARTIFACTS = artifact_safety.production_artifact_paths(REPO_ROOT)

# These are planning-time estimates only. Re-verify pricing before using cost as
# a decision input for a real migration choice.
PRICE_PER_MILLION_USD: dict[str, tuple[float, float]] = {
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.5": (5.00, 30.00),
}

TOutput = TypeVar("TOutput", bound=BaseModel)


class EvalHarnessError(RuntimeError):
    """Raised for evaluator configuration or fixture errors."""


class CandidateOutputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grouped_changelog_entries: dict[str, Any] | None = None
    breaking_changes: dict[str, Any] | None = None
    release_notes_body: dict[str, Any] | None = None


class OfflineCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    provider: providers.LLMProviderName
    model: str
    display_name: str
    outputs: CandidateOutputs = Field(default_factory=CandidateOutputs)


LLM_CALL_FIXTURE_FIELDS = {
    LLM_CALL_GROUPED_CHANGELOG_ENTRIES: "grouped_changelog_entries",
    LLM_CALL_BREAKING_CHANGES: "breaking_changes",
    LLM_CALL_RELEASE_NOTES_BODY: "release_notes_body",
}


class EvalFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str
    description: str
    source_repo: str
    release_tag: str
    release_url: str
    published_at: str
    image_number: int = 1
    starting_id: int = 1
    major_bump: bool = False
    expected_hard_gate_status: Literal["pass", "fail"] = "pass"
    expected_failure: str | None = None
    release_notes_prs: list[dict[str, Any]] = Field(default_factory=list)
    breaking_prs: list[dict[str, Any]] = Field(default_factory=list)
    offline_candidates: list[OfflineCandidate] = Field(default_factory=list)


class LiveCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    provider: providers.LLMProviderName
    model: str
    display_name: str


class ProviderCallRecord(BaseModel):
    call_name: str
    output_model: str
    prompt_chars: int
    max_output_tokens: int
    latency_seconds: float
    estimated_input_tokens: int
    estimated_output_tokens: int | None = None
    estimated_cost_usd: float | None = None


class HardCheck(BaseModel):
    name: str
    passed: bool
    details: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CandidateEvalResult(BaseModel):
    fixture_id: str
    candidate_id: str
    provider: providers.LLMProviderName
    model: str
    display_name: str
    hard_gate_status: Literal["pass", "fail"]
    expected_hard_gate_status: Literal["pass", "fail"]
    matched_expectation: bool
    provider_call_count: int
    provider_calls: list[ProviderCallRecord]
    hard_checks: list[HardCheck]
    errors: list[str]
    written_files: list[str] = Field(default_factory=list)
    generated_grouped_entries: list[dict[str, Any]] | None = None
    breaking_bullets: list[str] = Field(default_factory=list)
    release_notes_body: str = ""
    release_notes_markdown: str = ""


class RunSummary(BaseModel):
    run_id: str
    run_dir: str
    fixture_count: int
    candidate_result_count: int
    pass_count: int
    fail_count: int
    unexpected_count: int
    results: list[CandidateEvalResult]


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int | None) -> float | None:
    prices = PRICE_PER_MILLION_USD.get(model)
    if prices is None or output_tokens is None:
        return None
    input_price, output_price = prices
    return (input_tokens / 1_000_000 * input_price) + (output_tokens / 1_000_000 * output_price)


def make_provider_call_record(
    *,
    model: str,
    call_name: str,
    output_model: type[BaseModel],
    prompt: str,
    max_output_tokens: int,
    latency_seconds: float,
    parsed_output: BaseModel | None = None,
) -> ProviderCallRecord:
    input_tokens = estimate_tokens(prompt)
    output_tokens = estimate_tokens(parsed_output.model_dump_json()) if parsed_output else None
    return ProviderCallRecord(
        call_name=call_name,
        output_model=output_model.__name__,
        prompt_chars=len(prompt),
        max_output_tokens=max_output_tokens,
        latency_seconds=latency_seconds,
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_cost_usd=estimate_cost_usd(model, input_tokens, output_tokens),
    )


class OfflineFixtureProvider:
    """Structured-output provider backed by fixture JSON payloads."""

    def __init__(self, candidate: OfflineCandidate) -> None:
        self.provider = candidate.provider
        self.model = candidate.model
        self.outputs = candidate.outputs
        self.calls: list[ProviderCallRecord] = []

    def parse_structured_output(
        self,
        *,
        prompt: str,
        output_model: type[TOutput],
        max_output_tokens: int,
        call_name: str,
    ) -> TOutput:
        start = time.perf_counter()
        fixture_field = LLM_CALL_FIXTURE_FIELDS.get(call_name)
        if fixture_field is None:
            raise EvalHarnessError(f"Offline fixture lookup is not configured for LLM call {call_name!r}.")
        raw_output = getattr(self.outputs, fixture_field)
        if raw_output is None:
            self.calls.append(
                make_provider_call_record(
                    model=self.model,
                    call_name=call_name,
                    output_model=output_model,
                    prompt=prompt,
                    max_output_tokens=max_output_tokens,
                    latency_seconds=time.perf_counter() - start,
                )
            )
            raise EvalHarnessError(
                f"Offline candidate {self.provider}/{self.model} has no output for {call_name!r}."
            )

        parsed = output_model.model_validate(raw_output)
        self.calls.append(
            make_provider_call_record(
                model=self.model,
                call_name=call_name,
                output_model=output_model,
                prompt=prompt,
                max_output_tokens=max_output_tokens,
                latency_seconds=time.perf_counter() - start,
                parsed_output=parsed,
            )
        )
        return parsed


class MeasuredLiveProvider:
    """Thin measurement wrapper around the real structured-output provider seam."""

    def __init__(self, *, provider: providers.LLMProviderName, model: str, client: providers.StructuredLLMClient) -> None:
        self.provider = provider
        self.model = model
        self.client = client
        self.calls: list[ProviderCallRecord] = []

    def parse_structured_output(
        self,
        *,
        prompt: str,
        output_model: type[TOutput],
        max_output_tokens: int,
        call_name: str,
    ) -> TOutput:
        start = time.perf_counter()
        parsed = self.client.parse_structured_output(
            prompt=prompt,
            output_model=output_model,
            max_output_tokens=max_output_tokens,
            call_name=call_name,
        )
        self.calls.append(
            make_provider_call_record(
                model=self.model,
                call_name=call_name,
                output_model=output_model,
                prompt=prompt,
                max_output_tokens=max_output_tokens,
                latency_seconds=time.perf_counter() - start,
                parsed_output=parsed,
            )
        )
        return parsed


def check_pass(name: str, details: Sequence[str] | None = None, warnings: Sequence[str] | None = None) -> HardCheck:
    return HardCheck(name=name, passed=True, details=list(details or []), warnings=list(warnings or []))


def check_fail(name: str, details: Sequence[str], warnings: Sequence[str] | None = None) -> HardCheck:
    return HardCheck(name=name, passed=False, details=list(details), warnings=list(warnings or []))


def is_production_artifact_path(path: Path) -> bool:
    resolved = path.resolve()
    return resolved in PRODUCTION_ARTIFACTS or artifact_safety.is_production_artifact_path(
        resolved,
        repo_root=REPO_ROOT,
    )


def validate_repo_output_path(
    path: Path,
    *,
    production_message: str,
    repo_root_message: str,
    gitbook_message: str,
    allowed_repo_root: Path,
    outside_allowed_message: str,
) -> None:
    resolved = path.resolve()
    if is_production_artifact_path(resolved):
        raise EvalHarnessError(f"{production_message}: {resolved}")
    if resolved == REPO_ROOT.resolve():
        raise EvalHarnessError(repo_root_message)
    if resolved.is_relative_to((REPO_ROOT / "gitbook-release-notes").resolve()):
        raise EvalHarnessError(gitbook_message)
    if resolved.is_relative_to(REPO_ROOT.resolve()) and not resolved.is_relative_to(
        allowed_repo_root.resolve()
    ):
        raise EvalHarnessError(outside_allowed_message)


def validate_eval_run_dir(run_dir: Path) -> None:
    validate_repo_output_path(
        run_dir,
        production_message="Refusing to use production artifact as run directory",
        repo_root_message="Refusing to write evaluation reports directly into the repository root.",
        gitbook_message="Refusing to write evaluation reports under gitbook-release-notes/.",
        allowed_repo_root=REPO_ROOT / "eval-results",
        outside_allowed_message="Evaluation output inside this repo must live under eval-results/.",
    )


def validate_capture_output_path(output_path: Path) -> None:
    validate_repo_output_path(
        output_path,
        production_message="Refusing to overwrite production artifact",
        repo_root_message="Refusing to write a fixture over the repository root.",
        gitbook_message="Refusing to write fixtures under gitbook-release-notes/.",
        allowed_repo_root=DEFAULT_FIXTURES_DIR,
        outside_allowed_message="Fixture capture outputs inside this repo must live under tests/fixtures/changelog-evals/.",
    )


def safe_write_text(run_dir: Path, relative_path: str | Path, content: str) -> str:
    run_dir_resolved = run_dir.resolve()
    target = (run_dir / relative_path).resolve()
    if not target.is_relative_to(run_dir_resolved):
        raise EvalHarnessError(f"Refusing to write outside eval run directory: {target}")
    if is_production_artifact_path(target):
        raise EvalHarnessError(f"Refusing to write production artifact: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target.relative_to(run_dir_resolved).as_posix()


def safe_write_json(run_dir: Path, relative_path: str | Path, data: Any) -> str:
    return safe_write_text(run_dir, relative_path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def load_fixtures(fixtures_dir: Path, fixture_ids: set[str] | None = None) -> list[EvalFixture]:
    fixtures: list[EvalFixture] = []
    for fixture_path in sorted(fixtures_dir.glob("*.json")):
        fixture = EvalFixture.model_validate_json(fixture_path.read_text(encoding="utf-8"))
        if fixture_ids and fixture.fixture_id not in fixture_ids:
            continue
        if fixture.source_repo not in cfg.REPO_CONFIG:
            raise EvalHarnessError(f"Unknown source_repo in {fixture_path}: {fixture.source_repo}")
        fixtures.append(fixture)
    if fixture_ids:
        found = {fixture.fixture_id for fixture in fixtures}
        missing = sorted(fixture_ids - found)
        if missing:
            raise EvalHarnessError(f"Fixture id(s) not found: {', '.join(missing)}")
    return fixtures


def parse_live_candidate(value: str) -> LiveCandidate:
    parts = value.split(":", 2)
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            "Live candidates must use provider:model:label, e.g. openai:gpt-5.4-mini:OpenAI mini"
        )
    provider, model, label = parts
    provider = provider.strip().lower()
    model = model.strip()
    label = label.strip()
    if not provider:
        raise argparse.ArgumentTypeError("Live provider must be 'anthropic' or 'openai'.")
    try:
        provider_name = providers.normalize_llm_provider(provider)
    except RuntimeError as error:
        raise argparse.ArgumentTypeError("Live provider must be 'anthropic' or 'openai'.") from error
    if not model or not label:
        raise argparse.ArgumentTypeError("Live candidate model and label must be non-empty.")
    candidate_id = f"live-{provider_name}-{entry_builder.slugify_title(model)}"
    return LiveCandidate(
        candidate_id=candidate_id,
        provider=provider_name,
        model=model,
        display_name=label,
    )


def build_live_provider(candidate: LiveCandidate) -> MeasuredLiveProvider:
    if candidate.provider == providers.LLM_PROVIDER_ANTHROPIC:
        api_key = env.env_value("ANTHROPIC_API_KEY")
        if not api_key:
            raise EvalHarnessError("ANTHROPIC_API_KEY is required for live Anthropic evaluation.")
        client = providers.build_anthropic_structured_llm_client(
            api_key=api_key,
            model=candidate.model,
        )
        return MeasuredLiveProvider(
            provider=providers.LLM_PROVIDER_ANTHROPIC,
            model=candidate.model,
            client=client,
        )

    api_key = env.env_value("OPENAI_API_KEY")
    if not api_key:
        raise EvalHarnessError("OPENAI_API_KEY is required for live OpenAI evaluation.")
    try:
        client = providers.build_openai_structured_llm_client(
            api_key=api_key,
            model=candidate.model,
        )
    except RuntimeError as error:
        raise EvalHarnessError(str(error)) from error
    return MeasuredLiveProvider(
        provider=providers.LLM_PROVIDER_OPENAI,
        model=candidate.model,
        client=client,
    )


def fixture_candidates(
    fixture: EvalFixture,
    live_candidates: Sequence[LiveCandidate],
    candidate_filter: set[str] | None,
) -> list[OfflineCandidate | LiveCandidate]:
    candidates: list[OfflineCandidate | LiveCandidate] = [*fixture.offline_candidates, *live_candidates]
    if candidate_filter:
        candidates = [candidate for candidate in candidates if candidate.candidate_id in candidate_filter]
    if not candidates:
        raise EvalHarnessError(f"Fixture {fixture.fixture_id} has no candidates to evaluate.")
    return candidates


def provider_for_candidate(candidate: OfflineCandidate | LiveCandidate) -> OfflineFixtureProvider | MeasuredLiveProvider:
    if isinstance(candidate, OfflineCandidate):
        return OfflineFixtureProvider(candidate)
    return build_live_provider(candidate)


def changed_prs_for_grouping(fixture: EvalFixture) -> list[dict[str, Any]]:
    return fixture.release_notes_prs if fixture.release_notes_prs else fixture.breaking_prs


def body_prs_for_fixture(fixture: EvalFixture) -> list[dict[str, Any]]:
    breaking_keys = {(pr.get("repo"), int(pr["number"])) for pr in fixture.breaking_prs}
    return [
        pr
        for pr in fixture.release_notes_prs
        if (pr.get("repo"), int(pr["number"])) not in breaking_keys
    ]


def include_pr_links_for_fixture(fixture: EvalFixture) -> bool:
    return cfg.REPO_CONFIG[fixture.source_repo]["type"] == "oss"


def render_candidate_markdown(fixture: EvalFixture, breaking_bullets: list[str], body: str) -> str:
    return rendering.render_release_notes_section(
        release_tag=fixture.release_tag,
        published_at=fixture.published_at,
        image_number=fixture.image_number,
        source_repo=fixture.source_repo,
        release_url=fixture.release_url,
        breaking_bullets=breaking_bullets,
        body=body,
        force_breaking_placeholder=False,
        is_major_bump=fixture.major_bump,
    )


class CandidateEvaluationState:
    """Mutable state for one candidate run, including shared failure reporting."""

    def __init__(
        self,
        *,
        fixture: EvalFixture,
        candidate: OfflineCandidate | LiveCandidate,
        run_dir: Path,
    ) -> None:
        self.fixture = fixture
        self.candidate = candidate
        self.run_dir = run_dir
        self.candidate_dir = Path(fixture.fixture_id) / candidate.candidate_id
        self.provider: OfflineFixtureProvider | MeasuredLiveProvider | None = None
        self.hard_checks: list[HardCheck] = []
        self.errors: list[str] = []
        self.written_files: list[str] = []
        self.grouped_output: GroupedChangelogOutput | None = None
        self.generated_entries: list[dict[str, Any]] | None = None
        self.breaking_bullets: list[str] = []
        self.release_body = ""
        self.release_markdown = ""

    def fail(self, check_name: str, error: Exception) -> CandidateEvalResult:
        error_message = str(error)
        self.errors.append(error_message)
        self.hard_checks.append(check_fail(check_name, [error_message]))
        return self.finish()

    def finish(self) -> CandidateEvalResult:
        result = build_result(
            fixture=self.fixture,
            candidate=self.candidate,
            provider=self.provider,
            hard_checks=self.hard_checks,
            errors=self.errors,
            written_files=self.written_files,
            generated_grouped_entries=self.generated_entries,
            breaking_bullets=self.breaking_bullets,
            release_notes_body=self.release_body,
            release_notes_markdown=self.release_markdown,
        )
        return write_candidate_reports(self.run_dir, self.candidate_dir, result)


def evaluate_candidate(
    *,
    fixture: EvalFixture,
    candidate: OfflineCandidate | LiveCandidate,
    run_dir: Path,
) -> CandidateEvalResult:
    state = CandidateEvaluationState(fixture=fixture, candidate=candidate, run_dir=run_dir)
    has_changes = bool(fixture.release_notes_prs or fixture.breaking_prs)
    include_pr_links = include_pr_links_for_fixture(fixture)
    grouping_prs = changed_prs_for_grouping(fixture)
    body_prs = body_prs_for_fixture(fixture)

    if not has_changes:
        state.hard_checks.append(check_pass("no_changes_no_provider_calls"))
        return state.finish()

    try:
        validators.assert_unique_grouped_pr_numbers(grouping_prs)
        state.hard_checks.append(check_pass("input_pr_numbers_unambiguous"))
    except Exception as error:  # noqa: BLE001 - evaluator records any hard-gate failure
        return state.fail("input_pr_numbers_unambiguous", error)

    try:
        state.provider = provider_for_candidate(candidate)
        state.grouped_output = generation.generate_grouped_changelog_output(
            client=state.provider,
            prs=grouping_prs,
            source_repo=fixture.source_repo,
        )
        state.hard_checks.append(check_pass("grouped_structured_parse"))
        validators.validate_grouped_changelog_output(state.grouped_output, grouping_prs)
        state.hard_checks.append(check_pass("grouped_pr_assignment"))
        state.generated_entries = entry_builder.build_grouped_changelog_entries(
            grouped_output=state.grouped_output,
            prs=grouping_prs,
            source_repo=fixture.source_repo,
            published_at=fixture.published_at,
            starting_id=fixture.starting_id,
        )
        state.hard_checks.append(check_pass("candidate_changelog_render"))
        changelog_rel = state.candidate_dir / "candidate-changelog.json"
        state.written_files.append(safe_write_json(run_dir, changelog_rel, state.generated_entries))
        schema_validation.validate_changelog(run_dir / changelog_rel, SCHEMA_PATH)
        state.hard_checks.append(check_pass("candidate_changelog_schema"))
    except Exception as error:  # noqa: BLE001 - keep evaluating reportable hard gate failures
        return state.fail("grouped_changelog_hard_gate", error)

    try:
        if fixture.breaking_prs:
            breaking_output, warnings = generation.generate_breaking_changes_output(
                client=state.provider,
                breaking_prs=fixture.breaking_prs,
                source_repo=fixture.source_repo,
                include_pr_links=include_pr_links,
            )
            state.hard_checks.append(check_pass("breaking_structured_parse"))
            state.breaking_bullets = breaking_output.bullets
            state.hard_checks.append(check_pass("breaking_validator", warnings=warnings))
        else:
            state.hard_checks.append(check_pass("breaking_skipped_no_breaking_prs"))
    except Exception as error:  # noqa: BLE001
        return state.fail("breaking_hard_gate", error)

    try:
        if body_prs:
            body_output, warnings = generation.generate_release_notes_body_output(
                client=state.provider,
                prs=body_prs,
                source_repo=fixture.source_repo,
                include_pr_links=include_pr_links,
            )
            state.hard_checks.append(check_pass("release_notes_body_structured_parse"))
            state.release_body = body_output.content
            state.hard_checks.append(check_pass("release_notes_body_validator", warnings=warnings))
        else:
            state.hard_checks.append(check_pass("release_notes_body_skipped_no_body_prs"))
    except Exception as error:  # noqa: BLE001
        return state.fail("release_notes_body_hard_gate", error)

    state.release_markdown = render_candidate_markdown(
        fixture,
        state.breaking_bullets,
        state.release_body,
    )
    state.written_files.append(
        safe_write_text(run_dir, state.candidate_dir / "candidate-release-notes.md", state.release_markdown)
    )
    generated_outputs = {
        LLM_CALL_GROUPED_CHANGELOG_ENTRIES: state.grouped_output.model_dump(mode="json")
        if state.grouped_output
        else None,
        "breaking_bullets": state.breaking_bullets,
        LLM_CALL_RELEASE_NOTES_BODY: state.release_body,
    }
    state.written_files.append(
        safe_write_json(run_dir, state.candidate_dir / "generated-outputs.json", generated_outputs)
    )
    state.hard_checks.append(check_pass("evaluation_writes_confined_to_run_dir"))
    return state.finish()


def build_result(
    *,
    fixture: EvalFixture,
    candidate: OfflineCandidate | LiveCandidate,
    provider: OfflineFixtureProvider | MeasuredLiveProvider | None,
    hard_checks: list[HardCheck],
    errors: list[str],
    written_files: list[str],
    generated_grouped_entries: list[dict[str, Any]] | None = None,
    breaking_bullets: list[str] | None = None,
    release_notes_body: str = "",
    release_notes_markdown: str = "",
) -> CandidateEvalResult:
    hard_gate_status: Literal["pass", "fail"] = "pass" if all(check.passed for check in hard_checks) else "fail"
    return CandidateEvalResult(
        fixture_id=fixture.fixture_id,
        candidate_id=candidate.candidate_id,
        provider=candidate.provider,
        model=candidate.model,
        display_name=candidate.display_name,
        hard_gate_status=hard_gate_status,
        expected_hard_gate_status=fixture.expected_hard_gate_status,
        matched_expectation=hard_gate_status == fixture.expected_hard_gate_status,
        provider_call_count=len(provider.calls) if provider else 0,
        provider_calls=provider.calls if provider else [],
        hard_checks=hard_checks,
        errors=errors,
        written_files=written_files,
        generated_grouped_entries=generated_grouped_entries,
        breaking_bullets=breaking_bullets or [],
        release_notes_body=release_notes_body,
        release_notes_markdown=release_notes_markdown,
    )


def write_candidate_reports(run_dir: Path, candidate_dir: Path, result: CandidateEvalResult) -> CandidateEvalResult:
    report_json_rel = (candidate_dir / "report.json").as_posix()
    report_md_rel = (candidate_dir / "report.md").as_posix()
    final_result = result.model_copy(update={"written_files": [*result.written_files, report_json_rel, report_md_rel]})
    safe_write_json(run_dir, report_json_rel, final_result.model_dump(mode="json"))
    safe_write_text(run_dir, report_md_rel, render_candidate_report_md(final_result))
    return final_result


def render_candidate_report_md(result: CandidateEvalResult) -> str:
    lines = [
        f"# {result.fixture_id} — {result.display_name}",
        "",
        f"- Provider/model: `{result.provider}` / `{result.model}`",
        f"- Hard gate: **{result.hard_gate_status}**",
        f"- Expected: `{result.expected_hard_gate_status}`",
        f"- Provider calls: {result.provider_call_count}",
        "",
        "## Hard checks",
        "",
    ]
    for check in result.hard_checks:
        icon = "✅" if check.passed else "❌"
        lines.append(f"- {icon} `{check.name}`")
        for detail in check.details:
            lines.append(f"  - {detail}")
        for warning in check.warnings:
            lines.append(f"  - Warning: {warning}")
    if result.errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in result.errors)
    lines.extend(["", "## Manual scoring form", ""])
    lines.extend(manual_scoring_lines())
    return "\n".join(lines) + "\n"


def manual_scoring_lines() -> list[str]:
    rubric = [
        "dashboard grouping quality",
        "dashboard title quality",
        "dashboard description usefulness",
        "label correctness",
        "OSS vs Pro tone",
        "release-note structure",
        "release-note completeness",
        "noise avoidance",
        "breaking-change actionability",
        "missing important user-facing changes",
        "invented claims",
    ]
    return [f"- [ ] {item}: 1 / 2 / 3 / 4 / 5" for item in rubric]


def render_summary_md(summary: RunSummary) -> str:
    lines = [
        "# Changelog LLM evaluation summary",
        "",
        f"- Run id: `{summary.run_id}`",
        f"- Run directory: `{summary.run_dir}`",
        f"- Fixtures: {summary.fixture_count}",
        f"- Candidate results: {summary.candidate_result_count}",
        f"- Hard-gate pass/fail: {summary.pass_count} pass / {summary.fail_count} fail",
        f"- Unexpected outcomes: {summary.unexpected_count}",
        "",
        "## Results",
        "",
        "| Fixture | Candidate | Provider/model | Hard gate | Expected | Calls |",
        "| --- | --- | --- | --- | --- | ---: |",
    ]
    for result in summary.results:
        lines.append(
            "| {fixture} | {candidate} | `{provider}` / `{model}` | {status} | {expected} | {calls} |".format(
                fixture=result.fixture_id,
                candidate=result.display_name,
                provider=result.provider,
                model=result.model,
                status=result.hard_gate_status,
                expected=result.expected_hard_gate_status,
                calls=result.provider_call_count,
            )
        )
    lines.extend(["", "## Manual scoring form", ""])
    lines.extend(manual_scoring_lines())
    lines.extend(
        [
            "",
            "## Safety notes",
            "",
            "- This evaluator does not call `scripts/update_changelog.py main()`.",
            "- It writes reports under the eval run directory only.",
            "- Live provider calls require `--allow-live-provider-calls` plus explicit `--live-candidate` entries.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_comparison_html(summary: RunSummary) -> str:
    by_fixture: dict[str, list[CandidateEvalResult]] = {}
    for result in summary.results:
        by_fixture.setdefault(result.fixture_id, []).append(result)

    sections: list[str] = []
    for fixture_id, results in by_fixture.items():
        cards = []
        for result in results:
            grouped = json.dumps(result.generated_grouped_entries or [], indent=2, sort_keys=True)
            breaking = "\n".join(result.breaking_bullets) or "<none>"
            body = result.release_notes_body or "<none>"
            markdown = result.release_notes_markdown or "<not rendered>"
            cards.append(
                f"""
                <article class=\"candidate\">
                  <h3>{html.escape(result.display_name)}</h3>
                  <p><strong>Provider/model:</strong> {html.escape(result.provider)} / {html.escape(result.model)}</p>
                  <p><strong>Hard gate:</strong> {html.escape(result.hard_gate_status)}</p>
                  <h4>Grouped changelog entries</h4>
                  <pre>{html.escape(grouped)}</pre>
                  <h4>Breaking bullets</h4>
                  <pre>{html.escape(breaking)}</pre>
                  <h4>Release-note body</h4>
                  <pre>{html.escape(body)}</pre>
                  <h4>Rendered release-note sample</h4>
                  <pre>{html.escape(markdown)}</pre>
                </article>
                """
            )
        sections.append(
            f"""
            <section>
              <h2>{html.escape(fixture_id)}</h2>
              <div class=\"grid\">{''.join(cards)}</div>
            </section>
            """
        )

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <title>Changelog LLM evaluation comparison</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(28rem, 1fr)); gap: 1rem; }}
    .candidate {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem; background: #fafafa; }}
    pre {{ white-space: pre-wrap; background: white; border: 1px solid #eee; padding: 0.75rem; overflow-x: auto; }}
  </style>
</head>
<body>
  <h1>Changelog LLM evaluation comparison</h1>
  <p>Run id: <code>{html.escape(summary.run_id)}</code></p>
  <p>Provider and model labels are intentionally visible for PR-facing review.</p>
  {''.join(sections)}
</body>
</html>
"""


def run_eval(
    *,
    fixtures_dir: Path,
    output_root: Path,
    run_id: str | None,
    fixture_ids: set[str] | None,
    candidate_filter: set[str] | None,
    live_candidates: Sequence[LiveCandidate],
    allow_live_provider_calls: bool = False,
) -> RunSummary:
    if live_candidates and not allow_live_provider_calls:
        raise EvalHarnessError(
            "Live candidates require allow_live_provider_calls=True so provider calls are explicit."
        )

    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = (output_root / run_id).resolve()
    validate_eval_run_dir(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    fixtures = load_fixtures(fixtures_dir, fixture_ids)
    results: list[CandidateEvalResult] = []
    for fixture in fixtures:
        for candidate in fixture_candidates(fixture, live_candidates, candidate_filter):
            results.append(evaluate_candidate(fixture=fixture, candidate=candidate, run_dir=run_dir))

    summary = RunSummary(
        run_id=run_id,
        run_dir=str(run_dir),
        fixture_count=len(fixtures),
        candidate_result_count=len(results),
        pass_count=sum(1 for result in results if result.hard_gate_status == "pass"),
        fail_count=sum(1 for result in results if result.hard_gate_status == "fail"),
        unexpected_count=sum(1 for result in results if not result.matched_expectation),
        results=results,
    )
    safe_write_json(run_dir, "summary.json", summary.model_dump(mode="json"))
    safe_write_text(run_dir, "summary.md", render_summary_md(summary))
    safe_write_text(run_dir, "comparison.html", render_comparison_html(summary))
    return summary


def capture_fixture(*, input_path: Path, output_path: Path) -> None:
    fixture = EvalFixture.model_validate_json(input_path.read_text(encoding="utf-8"))
    validate_capture_output_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(fixture.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run-eval", help="Run static-fixture evaluation.")
    run_parser.add_argument("--fixtures-dir", type=Path, default=DEFAULT_FIXTURES_DIR)
    run_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    run_parser.add_argument("--run-id", default=None)
    run_parser.add_argument("--fixture-id", action="append", default=[])
    run_parser.add_argument("--candidate", action="append", default=[])
    run_parser.add_argument("--allow-live-provider-calls", action="store_true")
    run_parser.add_argument(
        "--live-candidate",
        action="append",
        type=parse_live_candidate,
        default=[],
        help="Explicit live candidate as provider:model:label. Requires --allow-live-provider-calls.",
    )

    capture_parser = subparsers.add_parser("capture-fixture", help="Normalize a local fixture JSON file.")
    capture_parser.add_argument("--input", type=Path, required=True)
    capture_parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "run-eval":
            if args.live_candidate and not args.allow_live_provider_calls:
                raise EvalHarnessError(
                    "Live candidates require --allow-live-provider-calls so provider calls are explicit."
                )
            summary = run_eval(
                fixtures_dir=args.fixtures_dir,
                output_root=args.output_root,
                run_id=args.run_id,
                fixture_ids=set(args.fixture_id) or None,
                candidate_filter=set(args.candidate) or None,
                live_candidates=args.live_candidate,
                allow_live_provider_calls=args.allow_live_provider_calls,
            )
            print(f"Wrote evaluation reports to {summary.run_dir}")
            print(f"Hard-gate results: {summary.pass_count} pass / {summary.fail_count} fail")
            if summary.unexpected_count:
                print(f"Unexpected outcomes: {summary.unexpected_count}")
                return 1
            return 0

        if args.command == "capture-fixture":
            capture_fixture(input_path=args.input, output_path=args.output)
            print(f"Wrote normalized fixture to {args.output}")
            return 0
    except EvalHarnessError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    parser.error(f"Unhandled command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
