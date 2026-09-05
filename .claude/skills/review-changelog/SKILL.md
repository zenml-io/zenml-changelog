---
name: review-changelog
description: Review and complete new changelog entries after automated PR creation. Use when there's a new changelog PR with entries that have placeholder URLs or empty fields that need review. Triggers on phrases like "review changelog", "complete changelog entries", "fix changelog PR", or when user mentions a PR with changelog updates.
---

# Review Changelog Entries

This skill helps complete new changelog entries after our automated release workflow creates a PR. The automation generates entries with placeholder values that need human review and completion.

## Context

- **Preview URL**: https://zenml-announcements-preview.vercel.app/ - Paste the final JSON here to preview how it will look
- **Schema docs**: See `changelog_schema/README.md` for field documentation
- **S3 images**: Feature images are uploaded to `public-flavor-logos` S3 bucket in `whats_new/` folder

## Required Fields (never remove)
- `id` - unique sequential number
- `slug` - URL-friendly identifier
- `title` - headline
- `description` - detailed description
- `published_at` - ISO 8601 datetime with Z suffix

## Optional Fields (remove if not provided)
- `feature_image_url` - screenshot/image URL (S3 bucket)
- `video_url` - YouTube embed URL
- `learn_more_url` - blog post or additional info URL
- `docs_url` - ZenML documentation URL
- `published` - boolean (default: true, can usually leave out)
- `highlight_until` - datetime to stop highlighting
- `should_highlight` - boolean, makes announcement pop up for users
- `audience` - "oss", "pro", or "all" (default: "all")
- `labels` - array of: "feature", "improvement", "bugfix", "deprecation"

## Workflow

### Step 0: Establish the Requested Scope

Review the PR or entries the user named. Do not expand a single-PR request into processing the whole queue. Explicit user instructions take precedence over this skill's guidelines; reuse decisions and authorization already given in the current task.

Only discover the queue when the user requests queue review. Widget PRs touch `changelog.json`, have the title prefix `Changelog widget:`, and commonly request `strickvl` as a reviewer:

```bash
gh pr list --repo zenml-io/zenml-changelog --state open --limit 50 \
  --json number,title,headRefName,createdAt,reviewRequests \
  --jq 'sort_by(.createdAt)'
```

Filter to the requested reviewer and scope, then report the oldest-first order and proceed. Read companion `Release notes:` PRs as evidence where needed; do not edit or merge them unless requested.

### Per-PR Loop

1. Verify the repository and working tree before checking out the requested PR. Preserve unrelated user changes; use an isolated checkout if switching would disturb them.
   ```bash
   gh pr checkout <number> --repo zenml-io/zenml-changelog
   git fetch origin main
   ```
   Inspect whether the branch is behind `origin/main`. For review-only work, inspect the diff without rebasing or editing files. Rebase only when needed for authorized fixes or shipping. For changelog conflicts, preserve unrelated entries, keep IDs unique and sequential, and preserve newest-first ordering.

2. Run Steps 1–3 below to investigate sources, prepare entry edits, and resolve material editorial questions. A review-only request produces findings and proposed edits; a request to complete or fix entries authorizes local edits.

3. Validate edited JSON with `uv run scripts/validate_changelog.py` and prepare the preview and final diff described in Step 4.

4. Commit, push, upload assets, or merge only when authorized by the user's task. This skill does not grant that authorization. Complete authorized preparation before asking about a remaining publishing decision, and do not ask again for authorization already given.

5. When shipping is requested, commit only the relevant files and push the PR branch. If an authorized rebase requires rewriting the remote branch, use `git push --force-with-lease`. Check current CI and review requirements before an authorized merge. If a required review is missing, report the gate and leave the PR ready for review; do not approve on the user's behalf or bypass branch protection.

6. For queue review, continue to the next PR after completing the requested review work; merging is not a prerequisite. For an authorized queue merge, refresh `origin/main` after each merge and reassess conflicts in the next PR.

### Step 1: Identify New Entries

After checking out the PR branch, find the new entries:

```bash
git branch --show-current
git diff origin/main...HEAD -- changelog.json
```

Parse the diff to identify entries that were added (look for lines starting with `+`). New entries typically have:
- Empty strings for `feature_image_url` and `video_url`
- Placeholder URLs like "https://example.com/REPLACE-ME" or "https://docs.zenml.io/REPLACE-ME"

### Step 2: Review Each Entry

Investigate the source PRs and check recent entries (last ~5) for overlapping content before asking editorial questions. Draft the proposed title, description, audience, labels, and verified links using the evidence and decisions already available.

#### 2.0 Inclusion and Editorial Decisions

For each entry, recommend keeping, removing, merging, or splitting it. Explain any overlap and the user-facing significance. Preserve the user's judgment about significance, grouping, and highlighting: ask when those choices remain unresolved and materially affect the result, rather than asking for every field by default.

Batch unresolved decisions across entries into a concise question using the available question interface or plain chat. Present concrete proposed entries and recommended choices first. While awaiting an answer, continue source research, link verification, and other independent work.

#### 2.0.1 Update Entry Content

Read the source PR description with `gh pr view <number> --repo <repo> --json title,body` and inspect further evidence where needed. Draft accurate user-facing copy. Apply routine factual corrections when local edits are authorized; present substantive editorial choices for the user's decision unless the user has already decided or delegated them. Do not require a second approval just to apply an approved choice.

#### 2.0.2 Split over-grouped entries (common)

The automation's LLM groups several PRs into 2–3 "buckets" per release to keep the widget compact, but that grouping is a guess and frequently fuses **unrelated features** into one entry (e.g. "nested dynamic pipelines AND a Databricks step operator", or "bigger secrets AND Run:AI settings"). Splitting these into separate cards gives each a clean headline, the correct label, and its own natural docs page.

**Heuristic for where to split:** count the distinct **source PRs** behind a bucket (from the GitBook markdown). Several unrelated PRs → split into one entry each. A cluster of genuinely small fixes (keyboard-interrupt handling, an import-failure fix) → keep them together as one "reliability roundup". A standalone example or a one-line fix bullet that the markdown lists under another release's "Fixed" section → usually drop it or fold it in, rather than give it a headline card.

Propose concrete split titles and ask about granularity only when it remains unresolved; use any preference already supplied. After splitting, **renumber** so ids stay unique and sequential, newest on top.

#### 2.1 Audience
- **oss** - Only open-source users see this
- **pro** - Only ZenML Pro users see this
- **all** - Everyone sees this (default)

#### 2.2 Labels
Verify the labels are correct. Options:
- `feature` - New functionality
- `improvement` - Enhancement to existing functionality
- `bugfix` - Bug fix
- `deprecation` - Deprecated features

#### 2.3 Feature Image
Preserve suitable existing images and use supplied assets. If the image decision remains material and unresolved, include it in the batched editorial question. Options:
- **No image** - This field will be removed from the entry
- **Already uploaded** - User provides existing S3 URL
- **Local file** - User has a local image that needs processing (see [Processing Local Images](#processing-local-images))

Images are hosted at: `https://public-flavor-logos.s3.eu-central-1.amazonaws.com/whats_new/`

#### 2.4 Video URL
Use an existing or supplied video demonstration and verify its embed URL. Ask only if a missing video materially affects the requested result.
- Format: `https://www.youtube-nocookie.com/embed/VIDEO_ID`
- If no video, this field will be removed from the entry

#### 2.5 Learn More URL
Use a relevant verified blog post or article from the source evidence or user input. Ask only if the destination remains a material choice.
- Usually a zenml.io/blog post
- If no blog post, this field will be removed from the entry

#### 2.6 Docs URL

Don't just ask the user to find a docs page — **investigate the source PRs first and suggest a verified URL**. The change behind an entry almost always shipped docs alongside the code, so the work is to find them:

1. **Find the source PRs for the entry.** For the **OSS path**, the companion `Release notes:` GitBook PR (usually already merged into `gitbook-release-notes/server-sdk.md`) lists every source PR with a link — extract the section for this release:
   ```bash
   awk '/## <TAG>/{f=1} f{print} /## <PREV_TAG>/{if(f)exit}' gitbook-release-notes/server-sdk.md
   ```
   For the **Pro path**, `pro-control-plane.md` omits PR links by convention, so you may only have the prose description (source repos are the private `zenml-cloud-api` / `zenml-cloud-ui`).

2. **Check each source PR for docs it added.** A PR that touches `docs/` or `*.md` files almost certainly has a docs page:
   ```bash
   gh pr view <PR_NUMBER> --repo zenml-io/zenml --json title,files \
     --jq '.title, (.files[].path | select(test("docs/|\\.md$")))'
   ```
   The PR file list is the **source of truth** for whether docs exist — do not guess from the entry text alone. (A PR with no `docs/` files, e.g. a pure API endpoint, legitimately has no docs page — leave `docs_url` off.)

3. **Map the `docs/book/*.md` file path to the live URL and verify it.** The live site does **not** mirror the file path (e.g. `docs/book/component-guide/step-operators/databricks.md` → `https://docs.zenml.io/stacks/stack-components/step-operators/databricks`). Verify every candidate with an HTTP check against a known-bad control so you don't trust a soft-404:
   ```bash
   probe() { curl -sL -o /dev/null -w "%{http_code}  %{url_effective}\n" "$1"; }
   probe "https://docs.zenml.io/<candidate-path>"
   probe "https://docs.zenml.io/this-path-should-404"   # control: must return 404
   ```
   Common path rewrites: `component-guide/...` → `stacks/stack-components/...`; `how-to/steps-pipelines/...` → `concepts/steps_and_pipelines/...`.

4. **Suggest the verified URL** to the user as the recommended option (they can override). If no source PR added docs, present "No docs link" as the recommendation.

#### 2.7 Should Highlight
Preserve existing highlighting unless the task requires a change. Recommend a value and include any unresolved highlighting decision in the batched question (highlighting pops up for users).
- Default: false
- Set to true for major features

### Step 3: Update changelog.json

When local edits are authorized, update each entry:
1. Update `audience` if different from default
2. Update or verify `labels`
3. Either set valid URLs or remove placeholder fields entirely
4. Set `should_highlight` if true

**Important**: Remove optional fields with empty/placeholder values rather than leaving them. A cleaner entry looks like:

```json
{
  "id": 10,
  "slug": "enhanced-pipeline-scheduling",
  "title": "Enhanced Pipeline Scheduling",
  "description": "You can now pause and resume schedules...",
  "published_at": "2026-01-14T09:20:00Z",
  "published": true,
  "audience": "all",
  "labels": ["improvement"],
  "docs_url": "https://docs.zenml.io/concepts/schedules"
}
```

### Step 4: Preview and Report

Present the final diff or proposed entries, validation result, and unresolved editorial decisions. Use the preview URL from Context when browser access is available and previewing is within the task's scope. Otherwise, give the user the preview URL and explain how to paste the JSON; state that visual verification remains outstanding.

For review-only work, finish with findings and proposed edits. For authorized local fixes, leave a validated diff. For authorized shipping, continue the per-PR loop through the requested commit, push, or merge and report its outcome. Do not hand authorized shipping work back to the user as generic "next steps."

## Example Batched Editorial Question

After reading sources and drafting the changes:

> I recommend merging the stack-update entry with the existing stack-management announcement because both describe the same shipped change. The separate scheduling entry has a verified docs link; I recommend keeping it without highlighting. Should I use those two editorial choices?

Ask this only if the choices remain unresolved. Do not repeat audience, labels, or asset questions already answered by evidence or prior user instructions.

## Processing Local Images

When a user has a local image file that needs to be used as a feature image:

### Step 1: Get the Local File Path

Use the supplied local path. Ask for the path only if the user requested an image and its file is missing.

### Step 2: Convert to AVIF

Use the `avif-image-compressor` skill to convert and compress the image:

```bash
~/.claude/skills/avif-image-compressor/scripts/convert_to_avif.sh "/path/to/image.png" --quality 30 --output "/tmp/output-name.avif"
```

- Quality 30 provides good visual fidelity for UI screenshots
- Typical compression: 80-90% size reduction

> **Note**: The AVIF compressor skill is available in the private `zenml-io/skills` repository. Team members who don't have it installed can clone it from there.

### Step 3: Upload to S3

When uploading is authorized, upload **both** the AVIF and the original PNG to the `public-flavor-logos` S3 bucket:

```bash
# Upload the AVIF version (used by the dashboard widget)
aws s3 cp /tmp/output-name.avif s3://public-flavor-logos/whats_new/output-name.avif --profile default

# Upload the PNG version (needed for email newsletters - many email clients don't support AVIF)
aws s3 cp /path/to/original-image.png s3://public-flavor-logos/whats_new/output-name.png --profile default
```

- Use the `default` AWS profile as required by the repository guidance.
- If it fails, report the error; do not switch accounts or profiles without authorization.

### Step 4: Get the Final URL

The final URLs will be:
```
https://public-flavor-logos.s3.eu-central-1.amazonaws.com/whats_new/output-name.avif  (dashboard)
https://public-flavor-logos.s3.eu-central-1.amazonaws.com/whats_new/output-name.png   (email)
```

Use the AVIF URL for the `feature_image_url` field in the changelog entry. The PNG version will be used when building email newsletters.

### Naming Convention

Use descriptive, kebab-case names for images:
- ✅ `enhanced-logs.avif`
- ✅ `pipeline-scheduling-ui.avif`
- ❌ `screenshot1.avif`
- ❌ `image.avif`

## Tips

- Batch questions where possible to reduce back-and-forth
- For entries with no supplementary content (no images, videos, blog, docs), just clean up the entry by removing placeholder fields
- The `published: true` field can usually be left in or removed (defaults to true)
- Make sure URLs are valid - schema validation will fail otherwise
