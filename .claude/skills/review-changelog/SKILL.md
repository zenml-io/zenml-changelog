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

### Step 1: Identify New Entries

Run these commands to find the current branch and new entries:

```bash
git branch --show-current
git diff main -- changelog.json
```

Parse the diff to identify entries that were added (look for lines starting with `+`). New entries typically have:
- Empty strings for `feature_image_url` and `video_url`
- Placeholder URLs like "https://example.com/REPLACE-ME" or "https://docs.zenml.io/REPLACE-ME"

### Step 2: Review Each Entry

For each new entry, use the `AskUserQuestion` tool to gather information. Ask about:

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

#### 2.3 Feature Image URL
Ask if there's a feature image/screenshot. If yes, get the URL.
- Images should be hosted at: `https://public-flavor-logos.s3.eu-central-1.amazonaws.com/whats_new/`
- If no image, this field will be removed from the entry

#### 2.4 Video URL
Ask if there's a video demonstration. If yes, get the YouTube embed URL.
- Format: `https://www.youtube-nocookie.com/embed/VIDEO_ID`
- If no video, this field will be removed from the entry

#### 2.5 Learn More URL
Ask if there's a blog post or article. If yes, get the URL.
- Usually a zenml.io/blog post
- If no blog post, this field will be removed from the entry

#### 2.6 Docs URL
Ask if there's relevant documentation. If yes, get the URL.
- Usually https://docs.zenml.io/...
- If no docs URL, this field will be removed from the entry

#### 2.7 Should Highlight
Ask if this announcement should be highlighted (pops up for users).
- Default: false
- Set to true for major features

### Step 3: Update changelog.json

Use the Edit tool to update each entry:
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

### Step 4: Prompt Preview

After updating all entries, tell the user:

> **Next Steps:**
> 1. Copy the updated `changelog.json` content
> 2. Go to https://zenml-announcements-preview.vercel.app/
> 3. Paste the JSON to preview how your entries will appear
> 4. If everything looks good, commit and push the changes

## Example AskUserQuestion Flow

For entry "Enhanced Pipeline Scheduling and Stack Management":

```
Questions to ask (can batch related questions):

1. Audience: Is this feature available to...
   - OSS users only
   - Pro users only
   - All users (Recommended)

2. Labels: The current labels are ["improvement"]. Is this correct?
   - Yes, keep as improvement
   - Change to feature
   - Change to bugfix
   - Other (specify)

3. Do you have a feature image URL for this entry?
   - No image
   - Yes (will prompt for URL)

4. Do you have a video URL?
   - No video
   - Yes (will prompt for URL)

5. Do you have a blog post URL (learn more)?
   - No blog post
   - Yes (will prompt for URL)

6. Do you have a docs URL?
   - No documentation link
   - Yes (will prompt for URL)

7. Should this entry be highlighted (pop up for users)?
   - No (default)
   - Yes, highlight this
```

## Tips

- Batch questions where possible to reduce back-and-forth
- For entries with no supplementary content (no images, videos, blog, docs), just clean up the entry by removing placeholder fields
- The `published: true` field can usually be left in or removed (defaults to true)
- Make sure URLs are valid - schema validation will fail otherwise
