# ZenML Changelog

Central hub for ZenML release metadata and release notes. This repo stores structured changelog data, GitBook-ready markdown, automation workflows, and validation schema used across ZenML products.

## Repository Structure

```
zenml-changelog/
├── changelog.json                  # Announcement entries consumed by the dashboard
├── .image_state                    # Tracks rotating header image (1-49) only
├── .consumed_sources_state         # Tracks consumed source windows/PRs to prevent replay
├── gitbook-release-notes/
│   ├── server-sdk.md               # OSS + dashboard release notes
│   ├── pro-control-plane.md        # Pro/Cloud release notes
│   └── README.md
├── changelog_schema/
│   ├── announcement-schema.json    # JSON Schema for changelog.json
│   └── README.md                   # Field documentation
├── scripts/
│   ├── update_changelog.py         # High-level automation flow and production writes
│   ├── changelog_config.py         # Repo config, labels, placeholders, tag helpers
│   ├── changelog_llm_outputs.py    # Strict structured-output Pydantic models
│   ├── changelog_llm_providers.py  # Anthropic/OpenAI clients and provider env parsing
│   ├── changelog_prompts.py        # Prompt builders for widget/release-note outputs
│   ├── changelog_validators.py     # Hard validators for LLM output contracts
│   ├── changelog_entry_builder.py  # Converts grouped output into changelog entries
│   ├── changelog_rendering.py      # Deterministic release-note rendering
│   ├── changelog_schema_validation.py # In-memory/file schema validation helpers
│   ├── workflow_result.py          # Structured workflow handoff and GitHub output writer
│   ├── consumed_sources.py         # Consumed-window/PR ledger models and validation
│   ├── source_windows.py           # Source-window resolution and PR collection
│   └── build_comparison_app.py     # Builds the offline blind-comparison web app from an eval run
├── comparison_app/
│   ├── template.html               # Blind A/B taste-test app shell (HTML/CSS/JS)
│   └── vendor/marked.min.js        # Vendored markdown renderer (inlined at build time)
├── .github/workflows/
│   ├── process-release.yml         # repository_dispatch receiver, runs automation, opens PR
│   └── validate-changelog.yml      # PR-time validation for changelog.json
├── design/plan.md                  # Automation design document
└── CLAUDE.md                       # Contributor guidance for Claude Code
```

## How the Automation Works

```mermaid
flowchart TD
    A[Source repo release] -->|repository_dispatch<br/>event_type: release-published| B[process-release.yml]
    B --> C[Run update_changelog.py]
    C --> D[changelog.json + .image_state]
    C --> E[gitbook-release-notes/*.md + .consumed_sources_state]
    D --> F[Schema validation]
    B --> G[Widget PR<br/>changelog/{repo}/{tag}]
    B --> H[Release notes PR<br/>release-notes/{repo}/{tag}]
```

- Trigger: One of two trigger repos (`zenml-io/zenml` or `zenml-io/zenml-cloud-api`) emits `repository_dispatch` (`release-published`).
- Receiver: `.github/workflows/process-release.yml` installs deps, runs `scripts/update_changelog.py`, validates `changelog.json`, then opens two PRs with reviewers and labels based on ownership: a widget PR for dashboard files and a release-notes PR for markdown plus the consumed-source ledger.
- Workflow handoff: `scripts/update_changelog.py` writes deterministic machine metadata to `changelog_workflow_result.json` (or the `CHANGELOG_WORKFLOW_RESULT` path). The workflow then runs `scripts/workflow_result.py write-github-outputs` to publish the stable GitHub Actions outputs: `has_changes`, `markdown_file`, `breaking_changes`, `needs_attention`, and `source_windows`. Stdout is only for human-readable logs, not workflow parsing.
- Script tasks: resolve each source repo's release window, skip windows/PRs already recorded in `.consumed_sources_state`, fetch `release-notes` PRs from the remaining bundled source windows, aggregate and deduplicate, generate 2-3 grouped changelog entries with the configured structured-output provider, rotate header image, update markdown, validate JSON, and update the consumed-source ledger after successful output.
- Breaking changes detection: PRs labeled `breaking-change` (and variants) are detected independently of `release-notes` and highlighted in a dedicated `### Breaking Changes` section near the top of release notes. Major version bumps always include this section (with a manual review prompt if no breaking PRs are found).

### PR Routing

**Widget PR** (updates `changelog.json` and `.image_state` only):
- Reviewers: `htahir1`, `znegrin`, `strickvl`
- Labels: `internal`, `x-squad`

**Release notes PR** (updates release-note markdown and `.consumed_sources_state`):

| Trigger Repository | Reviewers | Labels |
| --- | --- | --- |
| `zenml-io/zenml` (OSS) | schustmi, bcdurak | core-squad, internal |
| `zenml-io/zenml-cloud-api` (Pro) | schustmi, bcdurak | core-squad, internal |

## Two-Path Architecture

The automation uses a **two-path flow** where each trigger aggregates PRs from multiple bundled source repos:

| Trigger Repository | Bundled Sources | Files Updated |
| --- | --- | --- |
| `zenml-io/zenml` (OSS) | zenml + zenml-dashboard | `changelog.json`, `gitbook-release-notes/server-sdk.md` |
| `zenml-io/zenml-cloud-api` (Pro) | zenml-cloud-api + zenml-cloud-ui | `changelog.json`, `gitbook-release-notes/pro-control-plane.md` |

When a release is published on a trigger repo, the script automatically fetches PRs from all bundled source repos, aggregates them, and generates unified release notes. Bundled repos may have their own latest release tag, so the automation records each consumed source window (for example `zenml-cloud-ui 0.13.14 -> 0.13.15`) in `.consumed_sources_state`. On later trigger releases, an already-consumed window is skipped before any LLM prompt is built.

Consumed windows are **finalized windows**: if a PR gains a `release-notes` or breaking-change label after its window was recorded, that window is not reopened. This avoids replaying already-published release notes.

The committed bootstrap is intentionally narrow: it seeds only the confirmed PR75 Pro UI window from the investigation, not all historical OSS/Pro windows. Future successful automation runs build the ledger forward.

Generated PR bodies include a `Source windows` block. Reviewers should check which windows were included, skipped, or filtered, especially when the bundled repo did not advance with the trigger repo. `.consumed_sources_state` belongs in the release-notes PR, not the widget PR, so a source window is only marked consumed when the markdown that represents it is merged.

## Manual vs Automated Entries

- **Automated** (preferred): Triggered by releases; creates a PR with new JSON entries and markdown sections. Reviewers verify summaries, labels, and formatting before merge.
- **Manual**: Edit `changelog.json` (add new object with required fields) and prepend a section to `gitbook-release-notes/server-sdk.md` or `pro-control-plane.md` after frontmatter. Run validation before opening a PR.

## Required Secrets and Setup

- `ANTHROPIC_API_KEY` — Required only when `scripts/update_changelog.py` or live evaluation uses Anthropic.
- `OPENAI_API_KEY` — Required when production generation uses OpenAI or when live evaluation uses OpenAI.
- No-changes release runs do not initialize an LLM client and need no LLM provider key.
- `PRIVATE_REPO_TOKEN` — Optional PAT with access to private repos (used instead of `GITHUB_TOKEN` when set).
- Source repos need a dispatch token (e.g., `CHANGELOG_DISPATCH_TOKEN`) to send `repository_dispatch` events to this repo.

Provider and model selection:

- Code/script default: `CHANGELOG_LLM_PROVIDER` defaults to Anthropic, so rollback remains the code path of least surprise.
- Release workflow default: `.github/workflows/process-release.yml` sets `CHANGELOG_LLM_PROVIDER=${{ vars.CHANGELOG_LLM_PROVIDER || 'openai' }}` so production release runs use OpenAI unless a repo/org variable overrides it.
- Rollback: set `CHANGELOG_LLM_PROVIDER=anthropic`. Keep `ANTHROPIC_API_KEY` configured for that rollback path.
- `CHANGELOG_LLM_MODEL=<model>` is a global model override.
- OpenAI production routing, when no override is set:
  - `CHANGELOG_LLM_MODEL_GROUPED=gpt-5.4` for dashboard grouped changelog entries.
  - `CHANGELOG_LLM_MODEL_BREAKING=gpt-5.4` for breaking-change bullets.
  - `CHANGELOG_LLM_MODEL_RELEASE_NOTES=gpt-5.5` for release-note body prose.
- Per-call OpenAI model env vars override `CHANGELOG_LLM_MODEL`; blank values behave like missing values.
- `gpt-5.4-mini` is not a production default.

## Testing or Triggering Manually

- From a source repo, send a `repository_dispatch` with `event_type: release-published` and payload fields: `repo`, `repo_name`, `release_tag`, `release_name`, `release_url`, `release_body`, `published_at`, `is_prerelease`.
- In this repo, you can also re-run the `Process release` workflow from the Actions tab on a past dispatch if needed.
- Validate locally (optional) by running a JSON Schema check of `changelog.json` against `changelog_schema/announcement-schema.json`.
- Run the local pytest suite with the same dependency set used by CI:

```bash
uv run scripts/run_pytest.py
```

## Offline LLM Evaluation Harness

`scripts/evaluate_changelog_llms.py` is a non-production rehearsal space for comparing changelog LLM outputs. It reads static fixtures, runs provider/model outputs through the same hard validators used by `update_changelog.py`, and writes reports only under `eval-results/openai-migration/<run-id>/`.

Offline fixture run:

```bash
uv run scripts/evaluate_changelog_llms.py run-eval \
  --fixtures-dir tests/fixtures/changelog-evals \
  --output-root eval-results/openai-migration
```

Each run writes `summary.md`, `summary.json`, per-case reports, and a labeled `comparison.html` page. Provider/model names are visible in the reports so PR-facing review is not blind by accident.

Safety boundary:

- The evaluator does **not** call `scripts/update_changelog.py main()`.
- It does **not** write `changelog.json`, `gitbook-release-notes/*.md`, `.image_state`, or `.consumed_sources_state`.
- `eval-results/` is ignored and should not be committed.
- Unit tests use fake/offline provider outputs only.

Once live API keys are deliberately available, run live comparisons explicitly. Set only the key(s) for the live provider candidates you include:

```bash
ANTHROPIC_API_KEY=... OPENAI_API_KEY=... \
uv run scripts/evaluate_changelog_llms.py run-eval \
  --fixtures-dir tests/fixtures/changelog-evals \
  --output-root eval-results/openai-migration \
  --allow-live-provider-calls \
  --live-candidate anthropic:claude-sonnet-4-5-20250929:"Claude baseline" \
  --live-openai-routed-candidate "OpenAI routed|grouped=gpt-5.4,breaking=gpt-5.4,release=gpt-5.5"
```

Production provider configuration remains separate from evaluation:

- `CHANGELOG_LLM_PROVIDER=anthropic|openai`
- `CHANGELOG_LLM_MODEL=<global model override>`
- `CHANGELOG_LLM_MODEL_GROUPED=<dashboard grouped model override>`
- `CHANGELOG_LLM_MODEL_BREAKING=<breaking-change model override>`
- `CHANGELOG_LLM_MODEL_RELEASE_NOTES=<release-note body model override>`
- `ANTHROPIC_API_KEY` when `CHANGELOG_LLM_PROVIDER=anthropic`
- `OPENAI_API_KEY` when `CHANGELOG_LLM_PROVIDER=openai`

Rollback during migration is intentionally simple: set `CHANGELOG_LLM_PROVIDER=anthropic`.

## Blind Comparison Web App

`scripts/build_comparison_app.py` turns one evaluation run into a single, self-contained HTML page you can hand to colleagues for a **blind A/B preference test** ("The Changelog Taste Test"). It pairs the models' outputs head to head, hides which model produced which, and records each reviewer's picks so we can pick the model with the best human-preferred writing — not just the one that passes validators.

Build from an existing run (use `--model` to keep synthetic test-double candidates out):

```bash
uv run scripts/build_comparison_app.py \
  --run-dir eval-results/openai-migration/<run-id> \
  --target 24 \
  --model "Claude baseline" --model "OpenAI routed" --model "OpenAI 5.4" --model "OpenAI 5.5"
```

The output (`<run-dir>/blind-comparison.html` by default) is fully offline: the comparison data and a vendored markdown renderer are inlined, so a colleague just double-clicks the file — no server, no unzip, nothing leaves their laptop. They enter a name, pick the version they prefer for ~24 rounds (mouse or ← / → keys), then download a results JSON to paste into Discord.

How it stays trustworthy:

- Only `hard_gate_status: pass` outputs are paired (no broken output in the test).
- Pairs are sampled balanced across output types and model matchups, with a fixed `--seed` for reproducible builds.
- Model names live in the embedded data but are never shown; the page shuffles left/right per reviewer and records the true model behind each pick, so results aggregate by model.

Getting a *realistic* test (vs. the synthetic fixtures) is a three-step flow with your GitHub + API keys:

```bash
# 1. Capture the last few real OSS releases (zenml + zenml-dashboard, bundled) as fixtures.
#    Needs GITHUB_TOKEN (or PRIVATE_REPO_TOKEN); writes to tests/fixtures/changelog-evals/real/.
uv run scripts/evaluate_changelog_llms.py capture-release --last 4

# 2. Run the four models over those real fixtures (writes a new run under eval-results/).
ANTHROPIC_API_KEY=... OPENAI_API_KEY=... \
uv run scripts/evaluate_changelog_llms.py run-eval \
  --fixtures-dir tests/fixtures/changelog-evals/real \
  --allow-live-provider-calls \
  --live-candidate anthropic:claude-sonnet-4-5-20250929:"Claude baseline" \
  --live-openai-routed-candidate "OpenAI routed|grouped=gpt-5.4,breaking=gpt-5.4,release=gpt-5.5" \
  --live-candidate openai:gpt-5.4:"OpenAI 5.4" \
  --live-candidate openai:gpt-5.5:"OpenAI 5.5"

# 3. Build the taste-test app from that run.
uv run scripts/build_comparison_app.py \
  --run-dir eval-results/openai-migration/<new-run-id> --target 24 \
  --model "Claude baseline" --model "OpenAI routed" --model "OpenAI 5.4" --model "OpenAI 5.5"
```

`capture-release` reuses the automation's own PR-collection (previous-tag → date window → merged `release-notes`/breaking PRs), bundling `zenml` + `zenml-dashboard`, and writes `real-zenml-*.json` fixtures. The built HTML lives under the gitignored `eval-results/` tree and is a build artifact, not committed. Do not commit generated real fixtures from `tests/fixtures/changelog-evals/real/` unless explicitly requested.

## OSS GitHub Release Sync Contract

Release-notes PR bodies include a hidden `ZENML_CHANGELOG_SYNC_META` block. After a release-notes PR is merged, `.github/workflows/sync-zenml-release-notes.yml` parses that block with `scripts/sync_zenml_github_release_notes.py parse-sync-meta`.

The GitHub Release sync only proceeds when the parsed `source_repo` is `zenml-io/zenml`. The actual OSS sync step is currently pinned to `gitbook-release-notes/server-sdk.md`; the parsed `markdown_file` is required and must match that pinned path, but it is not used as a dynamic sync input yet.

## Uploading Feature Images

Images for changelog entries (`feature_image_url`) should be uploaded to the `public-flavor-logos` S3 bucket in the `whats_new/` folder.

```bash
# Upload (requires default AWS profile, not an assumed role)
aws s3api put-object \
  --bucket public-flavor-logos \
  --key whats_new/your-image-name.png \
  --body /path/to/local/image.png \
  --if-none-match "*" \
  --profile default
```

The bucket has upload-only permissions—no overwrites or deletes allowed. See `CLAUDE.md` for more details.

## Related Documentation

- Automation design: `design/plan.md`
- Schema details: `changelog_schema/README.md`
- Contributor guidance: `CLAUDE.md`
- GitBook notes: `gitbook-release-notes/README.md`
