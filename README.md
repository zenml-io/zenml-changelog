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
    C --> D[changelog.json]
    C --> E[gitbook-release-notes/server-sdk.md or pro-control-plane.md]
    D --> F[Schema validation]
    B --> G[Create PR<br/>changelog/{repo}-{tag}]
```

- Trigger: Source repos emit `repository_dispatch` (`release-published`).
- Receiver: `.github/workflows/process-release.yml` installs deps, runs `scripts/update_changelog.py`, validates `changelog.json`, then opens a PR with reviewers and labels.
- Script tasks: fetch `release-notes` PRs between releases, generate 2-3 grouped changelog entries (Anthropic structured outputs), rotate header image, update markdown, validate JSON.
- Breaking changes detection: PRs labeled `breaking-change` (and variants) are detected independently of `release-notes` and highlighted in a dedicated `### Breaking Changes` section near the top of release notes. Major version bumps always include this section (with a manual review prompt if no breaking PRs are found).

## Source Repositories and Targets

| Source repository | Type | Files updated here |
| --- | --- | --- |
| `zenml-io/zenml` | OSS core | `changelog.json`, `gitbook-release-notes/server-sdk.md` |
| `zenml-io/zenml-dashboard` | OSS UI | `changelog.json`, `gitbook-release-notes/server-sdk.md` |
| `zenml-io/zenml-cloud-ui` | Pro UI | `changelog.json`, `gitbook-release-notes/pro-control-plane.md` |
| `zenml-io/zenml-cloud-api` | Pro API | `changelog.json`, `gitbook-release-notes/pro-control-plane.md` |

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

## Related Documentation

- Automation design: `design/plan.md`
- Schema details: `changelog_schema/README.md`
- Contributor guidance: `CLAUDE.md`
- GitBook notes: `gitbook-release-notes/README.md`
