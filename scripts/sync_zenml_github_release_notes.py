#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests",
# ]
# ///
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import requests

GITHUB_API_BASE_URL = "https://api.github.com"


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def extract_release_section_from_server_sdk(markdown_text: str, release_tag: str) -> str:
    """Extract the markdown content for a release tag from the GitBook server-sdk file.

    The GitBook file is structured as repeated release sections beginning with:
      ## X.Y.Z (YYYY-MM-DD)

    We extract the section body (excluding the heading line), stopping at:
    - the next release heading (next `## `), or
    - a `***` separator line, or
    - EOF.

    We also strip GitBook-specific formatting that doesn't belong in GitHub Releases:
    - The trailing `***` separator
    - The "View full release on GitHub" link (redundant on GitHub)
    - HTML comments
    - The intro phrase "See what's new and improved in version X.Y.Z."
    - The header image banner (<img> tag)
    """
    if not release_tag.strip():
        raise ValueError("release_tag must be a non-empty string")

    tag = release_tag.strip()
    heading_re = re.compile(rf"^##\s+{re.escape(tag)}\s+\(", flags=re.MULTILINE)
    start_match = heading_re.search(markdown_text)
    if not start_match:
        raise RuntimeError(f"Release heading not found for tag '{tag}'")

    heading_line_end = markdown_text.find("\n", start_match.start())
    if heading_line_end == -1:
        # Heading is the last line; section content is empty.
        return ""

    content_start = heading_line_end + 1

    next_heading_match = re.search(r"^##\s+", markdown_text[content_start:], flags=re.MULTILINE)
    next_heading_index = content_start + next_heading_match.start() if next_heading_match else None

    separator_match = re.search(r"^\*\*\*\s*$", markdown_text[content_start:], flags=re.MULTILINE)
    separator_index = content_start + separator_match.start() if separator_match else None

    candidates = [idx for idx in [next_heading_index, separator_index] if idx is not None]
    content_end = min(candidates) if candidates else len(markdown_text)

    section = markdown_text[content_start:content_end].strip()

    # Remove redundant link lines for GitHub Releases.
    lines = section.splitlines()
    filtered_lines = [
        line
        for line in lines
        if not re.match(r"^\[View full release on GitHub\]\(.*\)\s*$", line.strip())
    ]
    section = "\n".join(filtered_lines).rstrip()

    # Remove any trailing separator markers that might have been included due to formatting variance.
    section = re.sub(r"\n?\*\*\*\s*$", "", section, flags=re.MULTILINE).rstrip()

    # Remove GitBook-specific formatting that doesn't belong in GitHub Releases:
    # 1. Remove HTML comments (e.g., <!-- ... -->)
    section = re.sub(r"<!--.*?-->", "", section, flags=re.DOTALL).strip()

    # 2. Remove the intro phrase "See what's new and improved in version X.Y.Z."
    section = re.sub(
        r"^See what's new and improved in version [0-9]+\.[0-9]+\.[0-9]+\.?\s*\n*",
        "",
        section,
        flags=re.MULTILINE | re.IGNORECASE,
    ).strip()

    # 3. Remove the image banner (<img src="..." ...>)
    section = re.sub(
        r"<img\s+[^>]*>\s*\n*",
        "",
        section,
        flags=re.IGNORECASE,
    ).strip()

    return section.strip()


def _github_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "zenml-changelog-release-notes-sync",
    }


def fetch_release_by_tag(token: str, repo: str, tag: str) -> Dict[str, Any]:
    url = f"{GITHUB_API_BASE_URL}/repos/{repo}/releases/tags/{tag}"
    resp = requests.get(url, headers=_github_headers(token), timeout=30)
    if resp.status_code == 404:
        raise RuntimeError(f"GitHub Release for tag '{tag}' not found in repo '{repo}' (404).")
    if not resp.ok:
        raise RuntimeError(
            f"Failed to fetch release by tag: {resp.status_code} {resp.text}"
        )
    payload = resp.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected response payload type when fetching release by tag.")
    return payload


def update_release_body(token: str, repo: str, release_id: int, body: str) -> None:
    url = f"{GITHUB_API_BASE_URL}/repos/{repo}/releases/{release_id}"
    resp = requests.patch(
        url,
        headers=_github_headers(token),
        json={"body": body},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(
            f"Failed to update release body: {resp.status_code} {resp.text}"
        )


def upsert_prepended_block(existing_body: str, new_block: str, tag: str) -> str:
    start_marker = f"<!-- ZENML_GITBOOK_RELEASE_NOTES_START tag={tag} -->"
    end_marker = f"<!-- ZENML_GITBOOK_RELEASE_NOTES_END tag={tag} -->"

    cleaned_existing = (existing_body or "").strip()

    block_re = re.compile(
        rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}\s*",
        flags=re.DOTALL,
    )
    cleaned_existing = re.sub(block_re, "", cleaned_existing).strip()

    managed_block = f"{start_marker}\n{new_block.strip()}\n{end_marker}".strip()

    insertion_heading = "## What's Changed"
    insert_idx = cleaned_existing.find(insertion_heading) if cleaned_existing else -1

    if insert_idx != -1:
        before = cleaned_existing[:insert_idx].rstrip()
        after = cleaned_existing[insert_idx:].lstrip()
        combined = f"{before}\n\n{managed_block}\n\n{after}".strip()
        return combined + "\n"

    if cleaned_existing:
        combined = f"{managed_block}\n\n{cleaned_existing}".strip()
        return combined + "\n"

    return managed_block.strip() + "\n"


def main() -> None:
    token = _require_env("ZENML_RELEASE_SYNC_TOKEN")
    release_tag = _require_env("RELEASE_TAG")

    target_repo = os.environ.get("TARGET_REPO", "zenml-io/zenml").strip() or "zenml-io/zenml"
    markdown_file = os.environ.get(
        "MARKDOWN_FILE", "gitbook-release-notes/server-sdk.md"
    ).strip() or "gitbook-release-notes/server-sdk.md"

    md_path = Path(markdown_file)
    if not md_path.exists():
        raise RuntimeError(f"Markdown file not found: {markdown_file}")

    markdown_text = md_path.read_text(encoding="utf-8")
    extracted = extract_release_section_from_server_sdk(markdown_text, release_tag)
    if not extracted.strip():
        raise RuntimeError(
            f"Extracted release notes are empty for tag '{release_tag}' from '{markdown_file}'."
        )

    release = fetch_release_by_tag(token=token, repo=target_repo, tag=release_tag)
    release_id = release.get("id")
    if not isinstance(release_id, int):
        raise RuntimeError("GitHub release payload missing integer 'id' field.")

    existing_body = release.get("body") or ""
    updated_body = upsert_prepended_block(existing_body=existing_body, new_block=extracted, tag=release_tag)

    if (existing_body or "").strip() == updated_body.strip():
        print(
            f"No changes needed: GitHub Release body for {target_repo}@{release_tag} is already up to date."
        )
        return

    update_release_body(token=token, repo=target_repo, release_id=release_id, body=updated_body)
    print(f"Synced GitBook release notes to GitHub Release: {target_repo}@{release_tag}")


if __name__ == "__main__":
    main()