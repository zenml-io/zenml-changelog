# Repository Guidelines

## Project Structure & Module Organization

This repository is the canonical source for ZenML release metadata and GitBook release notes.

- `changelog.json` stores dashboard announcement entries, newest first.
- `gitbook-release-notes/server-sdk.md` contains OSS release notes; `pro-control-plane.md` contains Pro release notes.
- `changelog_schema/` documents and validates the `changelog.json` format.
- `scripts/` contains the Python automation: `update_changelog.py`, `source_windows.py`, `consumed_sources.py`, and validation/sync helpers.
- `tests/` contains pytest coverage for changelog generation and consumed-source replay prevention.
- `.github/workflows/` runs dispatch processing, schema validation, and release-note sync workflows.

Do not add files from `design/` to git history.

## Build, Test, and Development Commands

- `uv run scripts/validate_changelog.py` validates `changelog.json` against `changelog_schema/announcement-schema.json`.
- `uv run pytest` runs the test suite.
- `uv run scripts/update_changelog.py` runs the release automation locally. It expects release payload environment variables and an `ANTHROPIC_API_KEY`.
- `./scripts/install-hooks.sh` installs the local pre-commit hook that validates `changelog.json`.

The scripts use PEP 723 inline dependencies, so there is no separate requirements file to install.

## Coding Style & Naming Conventions

Use Python 3.10+ compatible code, type hints where practical, and small functions with clear names. Keep JSON and Markdown edits deterministic: newest changelog entries first, release-note sections inserted after frontmatter, and stable ordering for consumed-source records.

Branch names, PR titles, and commit messages should be plain descriptive text without conventional commit prefixes. Example: `Prevent replaying consumed source release windows`, not `fix: prevent replay`.

## Testing Guidelines

Tests use `pytest` and live under `tests/` with names like `test_consumed_source_windows.py`. Add focused tests for replay prevention, schema transformations, source-window logic, and LLM-output validation when those behaviors change. If you edit code after running tests, rerun the relevant tests before finishing.

## Commit & Pull Request Guidelines

Stage only relevant files. Keep widget changes (`changelog.json`, `.image_state`) separate from release-note ledger changes (`gitbook-release-notes/*.md`, `.consumed_sources_state`) when matching the automation’s PR split.

PRs should describe what changed, which command validated it, and any source-window or release-note behavior reviewers should check. If changing prompts, schema, or automation architecture, update the relevant docs as well.

## Security & Configuration Tips

Never commit secrets. Use `ANTHROPIC_API_KEY` for local generation and `PRIVATE_REPO_TOKEN` only when private source repos must be accessed. Feature images should be uploaded to S3 with the `default` AWS profile, and both AVIF and PNG versions are expected.
