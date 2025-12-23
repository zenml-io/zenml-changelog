# ZenML Changelog

Central hub for ZenML release metadata and release notes. This repo stores structured changelog data, GitBook-ready markdown, automation workflows, and validation schema used across ZenML products.

## Repository Structure

```
zenml-changelog/
├── changelog.json                  # Announcement entries consumed by the dashboard
├── .image_state                    # Tracks rotating header image (1-49)
├── gitbook-release-notes/
│   ├── server-sdk.md               # OSS + dashboard release notes
│   ├── pro-control-plane.md        # Pro/Cloud release notes
│   └── README.md
├── changelog_schema/
│   ├── announcement-schema.json    # JSON Schema for changelog.json
│   └── README.md                   # Field documentation
├── scripts/
│   └── update_changelog.py         # Automation script: PR fetch, LLM summaries, updates
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
    C --> E[gitbook-release-notes/*.md]
    D --> F[Schema validation]
    B --> G[Widget PR<br/>changelog/{repo}/{tag}]
    B --> H[GitBook PR<br/>release-notes/{repo}/{tag}]
```

- Trigger: One of two trigger repos (`zenml-io/zenml` or `zenml-io/zenml-pro-api`) emits `repository_dispatch` (`release-published`).
- Receiver: `.github/workflows/process-release.yml` installs deps, runs `scripts/update_changelog.py`, validates `changelog.json`, then opens two PRs with reviewers and labels based on trigger repo.
- Script tasks: fetch `release-notes` PRs from all bundled source repos, aggregate and deduplicate, generate 2-3 grouped changelog entries (Anthropic structured outputs), rotate header image, update markdown, validate JSON.
- Breaking changes detection: PRs labeled `breaking-change` (and variants) are detected independently of `release-notes` and highlighted in a dedicated `### Breaking Changes` section near the top of release notes. Major version bumps always include this section (with a manual review prompt if no breaking PRs are found).

### PR Routing

**Widget PR** (updates `changelog.json` and `.image_state`):
- Reviewers: `htahir1`, `znegrin`, `strickvl`
- Labels: `internal`, `x-squad`

**GitBook PR** (updates release notes markdown):

| Trigger Repository | Reviewers | Labels |
| --- | --- | --- |
| `zenml-io/zenml` (OSS) | schustmi, bcdurak | core-squad, internal |
| `zenml-io/zenml-pro-api` (Pro) | htahir1, strickvl, znegrin | internal, x-squad |

## Two-Path Architecture

The automation uses a **two-path flow** where each trigger aggregates PRs from multiple bundled source repos:

| Trigger Repository | Bundled Sources | Files Updated |
| --- | --- | --- |
| `zenml-io/zenml` (OSS) | zenml + zenml-dashboard | `changelog.json`, `gitbook-release-notes/server-sdk.md` |
| `zenml-io/zenml-pro-api` (Pro) | zenml-pro-api + zenml-cloud-ui | `changelog.json`, `gitbook-release-notes/pro-control-plane.md` |

When a release is published on a trigger repo, the script automatically fetches PRs from all bundled source repos, aggregates them, and generates unified release notes.

## Manual vs Automated Entries

- **Automated** (preferred): Triggered by releases; creates a PR with new JSON entries and markdown sections. Reviewers verify summaries, labels, and formatting before merge.
- **Manual**: Edit `changelog.json` (add new object with required fields) and prepend a section to `gitbook-release-notes/server-sdk.md` or `pro-control-plane.md` after frontmatter. Run validation before opening a PR.

## Required Secrets and Setup

- `ANTHROPIC_API_KEY` — Required for LLM generation in `scripts/update_changelog.py`.
- `PRIVATE_REPO_TOKEN` — Optional PAT with access to private repos (used instead of `GITHUB_TOKEN` when set).
- Source repos need a dispatch token (e.g., `CHANGELOG_DISPATCH_TOKEN`) to send `repository_dispatch` events to this repo.

## Testing or Triggering Manually

- From a source repo, send a `repository_dispatch` with `event_type: release-published` and payload fields: `repo`, `repo_name`, `release_tag`, `release_name`, `release_url`, `release_body`, `published_at`, `is_prerelease`.
- In this repo, you can also re-run the `Process release` workflow from the Actions tab on a past dispatch if needed.
- Validate locally (optional) by running a JSON Schema check of `changelog.json` against `changelog_schema/announcement-schema.json`.

## Uploading Feature Images

Images for changelog entries (`feature_image_url`) should be uploaded to the `public-flavor-logos` S3 bucket in the `whats_new/` folder.

```bash
# Upload (requires default AWS profile, not an assumed role)
aws s3 cp /path/to/local/image.png \
  s3://public-flavor-logos/whats_new/your-image-name.png \
  --profile default
```

The bucket has upload-only permissions—no deletes allowed. See `CLAUDE.md` for more details.

## Related Documentation

- Automation design: `design/plan.md`
- Schema details: `changelog_schema/README.md`
- Contributor guidance: `CLAUDE.md`
- GitBook notes: `gitbook-release-notes/README.md`
