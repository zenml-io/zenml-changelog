# Repository Guidelines

## Project Structure & Module Organization

This repository is the canonical source for ZenML release metadata and GitBook release notes.

- `changelog.json` stores dashboard announcement entries, newest first.
- `gitbook-release-notes/server-sdk.md` contains OSS release notes; `pro-control-plane.md` contains Pro release notes.
- `changelog_schema/` documents and validates the `changelog.json` format.
- `scripts/` contains the Python automation: `update_changelog.py`, `workflow_result.py`, `source_windows.py`, `consumed_sources.py`, and validation/sync helpers.
- `scripts/build_comparison_app.py` builds the offline single-file blind A/B comparison web app from an eval run; `comparison_app/` holds its `template.html` shell and vendored `marked.min.js` renderer.
- `scripts/changelog_fixture_capture.py` turns real ZenML releases into eval fixtures (powering `evaluate_changelog_llms.py capture-release`); it uses dependency-injected GitHub collaborators so tests run with fakes and never hit the network.
- `tests/` contains pytest coverage for changelog generation and consumed-source replay prevention.
- `.github/workflows/` runs dispatch processing, schema validation, and release-note sync workflows.

Do not add files from `design/` to git history.
Do not commit intermediary plans, implementation reviews, prompt exports, oracle exports, or temporary investigation outputs unless explicitly requested. Keep them under ignored locations such as `design/`, `prompt-exports/`, `eval-results/`, `.agents/`, or `.claude/` when they are only working notes.
Do not commit generated investigation/review/plan outputs from `docs/investigations/`, `docs/plans/`, or `docs/reviews/`, and do not commit generated real eval fixtures under `tests/fixtures/changelog-evals/real/` unless explicitly requested.

## Task Scope & Follow-through

Carry authorized work through implementation, relevant validation, and final review. Make routine, reversible decisions from the available context. Ask only when missing information materially changes the outcome, and complete independent work while awaiting an answer.

Explicit user instructions take precedence over repository skill guidelines. Skills describe procedures; they do not independently authorize commits, pushes, merges, uploads, or live provider calls. Honor authorization already given in the current task without asking again.

If a repository instruction blocks authorized work, identify the exact file and rule, explain the conflict, and complete any independent work that can proceed.

## Build, Test, and Development Commands

- `uv run scripts/validate_changelog.py` validates `changelog.json` against `changelog_schema/announcement-schema.json`.
- `uv run scripts/run_pytest.py` runs the test suite with the same inline dependency set used by CI. Append pytest arguments to select tests.
- `uv run scripts/update_changelog.py` runs the release automation locally. It expects release payload environment variables plus `ANTHROPIC_API_KEY` for Anthropic generation or `OPENAI_API_KEY` for OpenAI generation. No-changes runs need no LLM provider key.
  - Script default provider is Anthropic; the release workflow defaults production runs to OpenAI unless `CHANGELOG_LLM_PROVIDER` is set differently. Rollback is `CHANGELOG_LLM_PROVIDER=anthropic`.
  - OpenAI routing defaults: `CHANGELOG_LLM_MODEL_GROUPED=gpt-5.4`, `CHANGELOG_LLM_MODEL_BREAKING=gpt-5.4`, and `CHANGELOG_LLM_MODEL_RELEASE_NOTES=gpt-5.5`. `CHANGELOG_LLM_MODEL` remains a global override; per-call vars override it. `gpt-5.4-mini` is not a production default.
- `./scripts/install-hooks.sh` installs the local pre-commit hook that validates `changelog.json`.

The scripts use PEP 723 inline dependencies, so there is no separate requirements file to install.

## Coding Style & Naming Conventions

Use Python 3.11+ compatible code for automation and tests; preserve the standalone schema validator's declared Python 3.10+ compatibility. Use type hints where practical and small functions with clear names. Keep JSON and Markdown edits deterministic: newest changelog entries first, release-note sections inserted after frontmatter, and stable ordering for consumed-source records.

Branch names, PR titles, and commit messages should be plain descriptive text without conventional commit prefixes. Example: `Prevent replaying consumed source release windows`, not `fix: prevent replay`.

## Testing Guidelines

Tests use `pytest` and live under `tests/` with names like `test_consumed_source_windows.py`. Add focused tests for replay prevention, schema transformations, source-window logic, and LLM-output validation when those behaviors change. If you edit code after running tests, rerun the relevant tests before finishing.

For changelog JSON changes, run the schema validator. For Python behavior changes, run affected tests through `uv run scripts/run_pytest.py`; run the full suite when changes affect shared generation, validation, or source-window behavior. For instruction-only changes, check the diff, referenced commands, and consistency across instruction files. Do not add tests that merely repeat the implementation. Broaden or repeat checks only when new changes, failures, or unresolved concerns justify it.

LLM provider tests must mock or fake providers. Do not make live Anthropic or OpenAI calls from pytest. Live comparisons belong only in explicit `scripts/evaluate_changelog_llms.py run-eval --allow-live-provider-calls ...` runs.

The evaluation harness is non-production. It must not call `scripts/update_changelog.py main()` and must not write `changelog.json`, `gitbook-release-notes/*.md`, `.image_state`, or `.consumed_sources_state`. Its local outputs go under ignored `eval-results/` directories and should not be committed. Keep provider-interface changes scoped to the task. Evaluation or comparison-app work should not change production provider behavior unless the requested work requires it.

`scripts/build_comparison_app.py` is also non-production: it only reads an eval run's `summary.json` plus fixtures and writes a single HTML build artifact (default under gitignored `eval-results/`). Keep it pure stdlib and keep the built page offline (no external `<script src>`/`<link href>`); the offline guarantee is asserted in `tests/test_build_comparison_app.py`. The browser UI is verified by opening the built file, not by unit tests.

## Commit & Pull Request Guidelines

Stage only relevant files. Keep widget changes (`changelog.json`, `.image_state`) separate from release-note ledger changes (`gitbook-release-notes/*.md`, `.consumed_sources_state`) when matching the automation’s PR split.

PRs should describe what changed, which command validated it, and any source-window or release-note behavior reviewers should check. If changing prompts, schema, or automation architecture, update the relevant docs as well.

## Security & Configuration Tips

Never commit secrets. Use `ANTHROPIC_API_KEY` only for Anthropic LLM work, `OPENAI_API_KEY` only for OpenAI LLM work or live OpenAI evals, and `PRIVATE_REPO_TOKEN` only when private source repos must be accessed. Feature images should be uploaded to S3 with the `default` AWS profile, and both AVIF and PNG versions are expected.
