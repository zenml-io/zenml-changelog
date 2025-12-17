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
- `scripts/validate_changelog.py` — Standalone schema validation (used by pre-commit hook).
- `scripts/install-hooks.sh` — Installs git pre-commit hook for local validation.
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
  - Opens **two PRs**:
    - **Widget PR** (`changelog/{repo_slug}/{tag}`): Updates `changelog.json` and `.image_state`. Reviewers: `htahir1,znegrin,strickvl`. Labels: `internal,x-squad`.
    - **GitBook PR** (`release-notes/{repo_slug}/{tag}`): Updates the appropriate markdown file. Reviewers and labels vary by source repo:
      - `zenml-dashboard` / `zenml-cloud-ui` → Reviewer: `Cahllagerfeld`, Labels: `documentation,internal,x-squad`
      - `zenml` → Reviewers: `schustmi,bcdurak`, Labels: `core-squad,internal`
      - `zenml-cloud-api` → Reviewers: `htahir1,strickvl,znegrin`, Labels: `internal,x-squad`
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
3. Validate locally (recommended): run `uv run scripts/validate_changelog.py`, or let the pre-commit hook catch issues on commit.
4. Open a PR; `validate-changelog.yml` will re-validate `changelog.json`.

## Schema Validation

- **Pre-commit hook**: Automatically validates `changelog.json` before each commit. Install with `./scripts/install-hooks.sh`.
- Automated on PRs touching `changelog.json` via `.github/workflows/validate-changelog.yml`.
- Automated in the dispatch workflow after generation via `process-release.yml`.
- Manual: run `uv run scripts/validate_changelog.py` to validate locally.

## Secrets

- `ANTHROPIC_API_KEY` (required) — Used by `scripts/update_changelog.py` for LLM summarization.
- `PRIVATE_REPO_TOKEN` (optional) — Use when the source repo is private (e.g., `zenml-cloud-ui`, `zenml-cloud-api`). If absent, the script falls back to `GITHUB_TOKEN` but will lack private repo access.

## Running Scripts Locally

This repo uses [uv](https://docs.astral.sh/uv/) with PEP 723 inline dependencies—no `requirements.txt` needed:

```bash
uv run scripts/update_changelog.py
```

## Uploading Feature Images to S3

Images for `feature_image_url` in changelog entries should be uploaded to the `public-flavor-logos` S3 bucket in the `whats_new/` folder.

**Important:** Use your `default` AWS profile (do not assume a role like `OrganizationAccountAccessRoleDev`).

```bash
# Upload a new image (will fail if file already exists)
aws s3api put-object \
  --bucket public-flavor-logos \
  --key whats_new/your-image-name.png \
  --body /path/to/local/image.png \
  --if-none-match "*" \
  --profile default

# List existing files in the folder
aws s3api list-objects-v2 \
  --bucket public-flavor-logos \
  --prefix whats_new/ \
  --profile default
```

The bucket enforces upload-only permissions (no delete/overwrite). If the file already exists, you'll get a `412 Precondition Failed` error—choose a different filename.

The resulting URL will be: `https://public-flavor-logos.s3.eu-central-1.amazonaws.com/whats_new/your-image-name.png`

## Tips for Working Here

- Keep `changelog.json` ordered newest-first; IDs must be unique and sequential.
- If automation produces a PR conflict in `changelog.json`, rebase and re-run the workflow or fix ordering manually.
- `.image_state` must stay committed so image rotation persists across runs.
- For OSS markdown, include PR links; for Pro markdown, keep concise and omit PR links.
- When adjusting prompts or schema, update `design/plan.md` for traceability.
- Never commit secrets; use repo/org secrets for workflows.
