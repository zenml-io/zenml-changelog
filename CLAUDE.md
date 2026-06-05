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
- `.image_state` — Persists rotating image index (1–49) for release note headers only.
- `.consumed_sources_state` — Dedicated ledger of consumed source release windows and PR keys, used to prevent bundled repo PRs from being summarized again on later trigger releases.
- `gitbook-release-notes/`
  - `server-sdk.md` — OSS release notes (bundles content from zenml + zenml-dashboard).
  - `pro-control-plane.md` — Pro release notes (bundles content from zenml-cloud-api + zenml-cloud-ui).
  - `README.md` — Notes for GitBook syncing.
- `changelog_schema/`
  - `announcement-schema.json` — Validation schema for `changelog.json`.
  - `README.md` — Field documentation and examples.
- `scripts/update_changelog.py` — High-level automation flow (source collection, LLM generation calls, JSON/markdown writes, image rotation, validation, workflow handoff).
- `scripts/changelog_config.py` — Shared repo configuration, label mapping, placeholder URLs, and tag prefix helpers.
- `scripts/changelog_llm_outputs.py` — Strict Pydantic models for structured LLM outputs.
- `scripts/changelog_llm_providers.py` — Anthropic/OpenAI structured-output clients and provider/model env parsing.
- `scripts/changelog_prompts.py` — Prompt builders for widget summaries, breaking changes, and release-note bodies.
- `scripts/changelog_validators.py` — Hard validators for model output and grouped PR assignment.
- `scripts/changelog_entry_builder.py` — Converts grouped LLM output into schema-compliant `changelog.json` entries.
- `scripts/changelog_rendering.py` — Deterministic release-note header/body/footer assembly and markdown insertion.
- `scripts/changelog_schema_validation.py` — In-memory and file-based `changelog.json` schema validation.
- `scripts/workflow_result.py` — Deterministic workflow-result JSON model and GitHub Actions output writer.
- `scripts/consumed_sources.py` — Consumed-window/PR ledger models, structured provenance, and read-time validation.
- `scripts/source_windows.py` — Source-window resolution, replay prevention, and PR collection.
- `scripts/build_comparison_app.py` — Builds the offline single-file blind A/B comparison web app from an eval run.
- `scripts/changelog_fixture_capture.py` — Turns real ZenML releases into eval fixtures (dependency-injected PR collection; powers `evaluate_changelog_llms.py capture-release`).
- `scripts/validate_changelog.py` — Standalone schema validation (used by pre-commit hook).
- `scripts/install-hooks.sh` — Installs git pre-commit hook for local validation.
- `comparison_app/` — Source for the blind-comparison web app: `template.html` (app shell) and `vendor/marked.min.js` (vendored markdown renderer, inlined at build time).
- `.github/workflows/`
  - `process-release.yml` — Receives `repository_dispatch` `release-published`, runs the script, validates, opens a PR.
  - `validate-changelog.yml` — PR-time schema validation for `changelog.json`.
- `design/plan.md` — Architecture/design for automation.
- `.claude/settings.local.json` — Local Claude settings (do not commit secrets).

## Automation System

**Flow**: Source repo release → `repository_dispatch` → `process-release.yml` → `scripts/update_changelog.py` → validation → PR.

- Trigger: `repository_dispatch` with `event_type: release-published` from one of two trigger repos.
- **Two-Path Architecture**:
  - **OSS Path**: Triggered by `zenml-io/zenml` release → aggregates PRs from zenml + zenml-dashboard → updates `server-sdk.md`
  - **Pro Path**: Triggered by `zenml-io/zenml-cloud-api` release → aggregates PRs from zenml-cloud-api + zenml-cloud-ui → updates `pro-control-plane.md`
- Workflow: `.github/workflows/process-release.yml`
  - Uses `uv run` to execute the script (deps declared inline via PEP 723).
  - Runs `scripts/update_changelog.py` with payload env vars (`SOURCE_REPO`, `RELEASE_TAG`, `RELEASE_URL`, `PUBLISHED_AT`, etc.), then uses `scripts/workflow_result.py write-github-outputs` to publish the stable workflow outputs.
  - Validates `changelog.json` against `changelog_schema/announcement-schema.json` via `cardinalby/schema-validator-action@v3`.
  - Opens **two PRs** with separate ownership:
    - **Widget PR** (`changelog/{repo_slug}/{tag}`): Updates `changelog.json` and `.image_state` only. Reviewers: `htahir1,znegrin,strickvl`. Labels: `internal,x-squad`.
    - **Release notes PR** (`release-notes/{repo_slug}/{tag}`): Updates the appropriate markdown file and `.consumed_sources_state`. Reviewers: `schustmi,bcdurak`. Labels: `core-squad,internal`.
- Script: `scripts/update_changelog.py`
  - Uses `REPO_CONFIG` with nested `sources[]` arrays to define bundled repos per trigger.
  - For each source repo: finds its previous tag, computes release window, and checks `.consumed_sources_state` before fetching PRs.
  - Already-consumed windows are finalized windows: they are skipped before the LLM prompt is built and are not reopened for late-labeled PRs. Already-consumed repo-qualified PR keys are filtered as a second guardrail.
  - Aggregates and deduplicates PRs across all sources using `(repo, pr_number)` keys.
  - Generates 2-3 grouped changelog entries via the configured structured-output provider. The script default is Anthropic; the release workflow defaults production generation to OpenAI unless `CHANGELOG_LLM_PROVIDER` is set differently.
  - Prepends entries to `changelog.json`, validates against `announcement-schema.json`.
  - Rotates header image using `.image_state` (cycles 1–49).
  - Generates markdown section (OSS links PRs; Pro omits PR links) and inserts after frontmatter in the appropriate file.
  - Updates `.consumed_sources_state` only after successful changelog and markdown updates, then writes structured source-window metadata for PR bodies to `changelog_workflow_result.json`.
  - Prints summary and exits; workflow keeps `.consumed_sources_state` in the release-notes PR, so a source window is only marked consumed when the markdown that represents it is merged.
  - When `CHANGELOG_OPENAI_SHADOW_MODE=true`, also generates OpenAI shadow-mode comment files for reviewers using the same routed OpenAI config as production OpenAI. Each output section is labeled by provider, model, and output type, and is posted to the generated widget/release-notes PRs. Shadow output is never used to write production artifacts.

## Blind Comparison Web App

`scripts/build_comparison_app.py` reads one `eval-results/openai-migration/<run-id>/summary.json` and emits a single self-contained `blind-comparison.html` for human preference review ("The Changelog Taste Test"). It pairs passing model outputs (release notes, changelog entries, breaking-change bullets) head to head, samples a balanced set (`--target`, fixed `--seed`), and inlines both the data and a vendored markdown renderer so the file runs offline with no server.

- Use `--model "<display name>"` (repeatable) to restrict to real models and exclude synthetic `fake-*` candidates.
- Blind by design: model names are embedded but never shown on screen; the page randomizes left/right per reviewer and records the true model behind each pick. Reviewers download a results JSON to paste into Discord.
- The built HTML is a gitignored artifact under `eval-results/`. The builder is pure stdlib; `comparison_app/template.html` holds the UI and `comparison_app/vendor/marked.min.js` is the offline renderer.
- Tests live in `tests/test_build_comparison_app.py` (pure-logic plus the offline-guarantee assertion that the built HTML has no external `<script src>`/`<link href>`). The UI/animation layer is verified by opening the built file in a browser, not by unit tests.
- For a realistic test, `evaluate_changelog_llms.py capture-release --last N` captures real OSS releases (bundling `zenml` + `zenml-dashboard`) into `tests/fixtures/changelog-evals/real/` (a subdir, so it never breaks the offline tests that scan the synthetic fixtures); then run a live eval with `--fixtures-dir tests/fixtures/changelog-evals/real` and build the app from that run. Capture logic lives in `scripts/changelog_fixture_capture.py` and is tested with fake GitHub collaborators (no live calls). Needs `GITHUB_TOKEN`/`PRIVATE_REPO_TOKEN` at run time.

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

## Secrets and Provider Configuration

- `ANTHROPIC_API_KEY` — Required when production generation uses Anthropic. Keep this configured for rollback.
- `OPENAI_API_KEY` — Required when production generation uses OpenAI. Also required to produce workflow shadow comments when `CHANGELOG_OPENAI_SHADOW_MODE=true`; if absent or blank, shadow comments are skipped and the production workflow continues.
- `CHANGELOG_LLM_PROVIDER=anthropic|openai` — Optional production provider override. The script default is Anthropic; `process-release.yml` defaults release runs to OpenAI. Roll back the workflow by setting `CHANGELOG_LLM_PROVIDER=anthropic`.
- `CHANGELOG_LLM_MODEL=<model>` — Optional global model override.
- `CHANGELOG_LLM_MODEL_GROUPED=<model>` — Optional OpenAI model override for dashboard grouped changelog entries. Default: `gpt-5.4`.
- `CHANGELOG_LLM_MODEL_BREAKING=<model>` — Optional OpenAI model override for breaking-change bullets. Default: `gpt-5.4`.
- `CHANGELOG_LLM_MODEL_RELEASE_NOTES=<model>` — Optional OpenAI model override for release-note body prose. Default: `gpt-5.5`.
- Per-call OpenAI model env vars override `CHANGELOG_LLM_MODEL`; blank values behave like missing values. `gpt-5.4-mini` is not a production default.
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

**Important:** Always upload both AVIF and PNG versions of feature images. The AVIF version is used by the dashboard widget (smaller file size), but the PNG version is needed for email newsletters since many email clients (Outlook, Brevo preview) don't support AVIF.

## Naming Conventions

**Branch names**, **PR titles**, and **commit messages** should all use plain descriptive text without conventional commit prefixes (no `fix:`, `feat:`, `docs:`, etc.).

- ✅ `fix-release-notes-formatting` (branch)
- ✅ `Fix release notes formatting for GitHub sync` (PR title)
- ✅ `Strip GitBook-specific formatting from synced release notes` (commit)
- ❌ `fix/release-notes-formatting` (no type prefix)
- ❌ `fix: release notes formatting` (no colon syntax)

## Tips for Working Here

- Keep `changelog.json` ordered newest-first; IDs must be unique and sequential.
- If automation produces a PR conflict in `changelog.json`, rebase and re-run the workflow or fix ordering manually.
- `.image_state` must stay committed so image rotation persists across runs; keep it image-only.
- `.consumed_sources_state` must stay committed so source windows/PRs are consumed once. Its current bootstrap is intentionally narrow, and recorded windows are finalized: late-labeled PRs inside them are ignored rather than replaying old release notes. If duplicate release notes appear, inspect this file rather than overloading `.image_state`.
- For OSS markdown, include PR links; for Pro markdown, keep concise and omit PR links.
- When adjusting prompts or schema, update `design/plan.md` for traceability.
- Do not commit intermediary plans, implementation reviews, prompt exports, oracle exports, or temporary investigation outputs unless explicitly requested. Keep working notes under ignored locations such as `design/`, `prompt-exports/`, `eval-results/`, `.agents/`, or `.claude/`.
- Never commit secrets; use repo/org secrets for workflows.
- IMPORTANT: **Before opening a PR or making a large commit**, always run `/simplify` to review changed code for reuse opportunities, quality issues, and efficiency improvements. Fix any issues it finds before committing.
