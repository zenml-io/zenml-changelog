# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## Repository Purpose

This repo is the canonical source of ZenML release metadata:
- `changelog.json` feeds the ZenML dashboard "What’s New" widget.
- `gitbook-release-notes/server-sdk.md` and `gitbook-release-notes/pro-control-plane.md` power GitBook docs for OSS and Pro.
- `.github/workflows/` orchestrates automated changelog generation from upstream releases.
- `changelog_schema/` defines and documents the JSON schema for announcements.

## Directory Structure

- `changelog.json` — Array of announcements consumed by the dashboard.
- `.image_state` — Persists rotating image index (1–49) for release note headers.
- `gitbook-release-notes/`
  - `server-sdk.md` — OSS/UI release notes (zenml, zenml-dashboard).
  - `pro-control-plane.md` — Pro/Cloud release notes (zenml-cloud-ui, zenml-cloud-api).
  - `README.md` — Notes for GitBook syncing.
- `changelog_schema/`
  - `announcement-schema.json` — Validation schema for `changelog.json`.
  - `README.md` — Field documentation and examples.
- `scripts/update_changelog.py` — Main automation script (fetch PRs, LLM summaries, update JSON/markdown, image rotation, validation).
- `.github/workflows/`
  - `process-release.yml` — Receives `repository_dispatch` `release-published`, runs the script, validates, opens a PR.
  - `validate-changelog.yml` — PR-time schema validation for `changelog.json`.
- `design/plan.md` — Architecture/design for automation.
- `.claude/settings.local.json` — Local Claude settings (do not commit secrets).

## Automation System

**Flow**: Source repo release → `repository_dispatch` → `process-release.yml` → `scripts/update_changelog.py` → validation → PR.

- Trigger: `repository_dispatch` with `event_type: release-published` from source repos.
- Workflow: `.github/workflows/process-release.yml`
  - Uses `uv run` to execute the script (deps declared inline via PEP 723).
  - Runs `scripts/update_changelog.py` with payload env vars (`SOURCE_REPO`, `RELEASE_TAG`, `RELEASE_URL`, `PUBLISHED_AT`, etc.).
  - Validates `changelog.json` against `changelog_schema/announcement-schema.json` via `cardinalby/schema-validator-action@v3`.
  - Opens a PR on branch `changelog/{repo_name}-{release_tag}` with labels `automated,changelog` and reviewers `htahir1,strickvl`.
- Script: `scripts/update_changelog.py`
  - Determines repo config (OSS/Pro, markdown target, default branch) from `REPO_CONFIG`.
  - Finds previous release tag, fetches merged PRs with `release-notes` label in the date range.
  - Generates per-PR changelog entries via Anthropic structured outputs (validated with Pydantic models).
  - Prepends entries to `changelog.json`, validates against `announcement-schema.json`.
  - Rotates header image using `.image_state` (cycles 1–49).
  - Generates markdown section (OSS links PRs; Pro omits PR links) and inserts after frontmatter in the appropriate file.
  - Prints summary and exits; workflow handles PR creation.

## Manually Adding Changelog Entries

1. Edit `changelog.json`:
   - Add a new object with required fields: `id` (next sequential number), `slug`, `title`, `description`, `published_at` (ISO8601 with `Z`), `audience` (`oss|pro|all`), `labels` (`bugfix|deprecation|improvement|feature`).
   - Optional fields: `feature_image_url`, `learn_more_url`, `docs_url`, `highlight_until`, `should_highlight`, `video_url`, `published`.
2. Update release notes:
   - OSS: insert a new section at the top of `gitbook-release-notes/server-sdk.md` after frontmatter.
   - Pro: insert at the top of `gitbook-release-notes/pro-control-plane.md` after frontmatter.
3. Validate locally (recommended): use `cardinalby/schema-validator-action@v3` or run a local `jsonschema` check against `changelog_schema/announcement-schema.json`.
4. Open a PR; `validate-changelog.yml` will re-validate `changelog.json`.

## Schema Validation

- Automated on PRs touching `changelog.json` via `.github/workflows/validate-changelog.yml`.
- Automated in the dispatch workflow after generation via `process-release.yml`.
- Manual: run a JSON Schema check against `changelog_schema/announcement-schema.json` if editing locally.

## Secrets

- `ANTHROPIC_API_KEY` (required) — Used by `scripts/update_changelog.py` for LLM summarization.
- `PRIVATE_REPO_TOKEN` (optional) — Use when the source repo is private (e.g., `zenml-cloud-ui`, `zenml-cloud-api`). If absent, the script falls back to `GITHUB_TOKEN` but will lack private repo access.

## Running Scripts Locally

This repo uses [uv](https://docs.astral.sh/uv/) with PEP 723 inline dependencies—no `requirements.txt` needed:

```bash
uv run scripts/update_changelog.py
```

## Tips for Working Here

- Keep `changelog.json` ordered newest-first; IDs must be unique and sequential.
- If automation produces a PR conflict in `changelog.json`, rebase and re-run the workflow or fix ordering manually.
- `.image_state` must stay committed so image rotation persists across runs.
- For OSS markdown, include PR links; for Pro markdown, keep concise and omit PR links.
- When adjusting prompts or schema, update `design/plan.md` for traceability.
- Never commit secrets; use repo/org secrets for workflows.
