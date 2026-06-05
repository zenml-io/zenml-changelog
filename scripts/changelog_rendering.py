#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import List

try:
    from scripts.changelog_config import REPO_CONFIG
except ModuleNotFoundError:  # pragma: no cover
    from changelog_config import REPO_CONFIG  # type: ignore[no-redef]

def render_release_header(
    release_tag: str,
    published_at: str,
    image_number: int,
    source_repo: str,
) -> str:
    """Render the deterministic header portion of release notes."""
    config = REPO_CONFIG[source_repo]
    repo_type = config["type"]
    alt_prefix = "ZenML Pro" if repo_type == "pro" else "ZenML"

    return (
        f"## {release_tag} ({published_at[:10]})\n\n"
        f"See what's new and improved in version {release_tag}.\n\n"
        f'<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/{image_number}.jpg" '
        f'align="left" alt="{alt_prefix} {release_tag}" width="800">\n\n'
    )

def render_breaking_section(
    bullets: List[str],
    force_placeholder: bool,
    is_major_bump: bool,
) -> str:
    """Render the Breaking Changes section.

    Returns empty string if no bullets and not forced.
    If forced (major bump) but no bullets, returns placeholder text.
    """
    bullets_clean = [bullet.strip() for bullet in (bullets or []) if bullet and bullet.strip()]
    if bullets_clean:
        formatted = "\n".join(f"* {bullet}" for bullet in bullets_clean)
        return f"### Breaking Changes\n\n{formatted}\n\n"

    forced = force_placeholder or is_major_bump
    if not forced:
        return ""

    placeholder = (
        "* This is a major release. No PRs were labeled as breaking changes; "
        "please review manually for any breaking changes."
    )
    return f"### Breaking Changes\n\n{placeholder}\n\n"

def render_release_footer(source_repo: str, release_url: str) -> str:
    """Render the deterministic footer portion of release notes."""
    config = REPO_CONFIG[source_repo]

    footer_parts: List[str] = []
    if config.get("include_release_link"):
        footer_parts.append(f"[View full release on GitHub]({release_url})")
    if config.get("include_compatibility_note"):
        footer_parts.append("> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.")

    if footer_parts:
        return "\n\n".join(footer_parts) + "\n\n***"
    return "***"

def render_release_notes_section(
    *,
    release_tag: str,
    published_at: str,
    image_number: int,
    source_repo: str,
    release_url: str,
    breaking_bullets: List[str],
    body: str,
    force_breaking_placeholder: bool,
    is_major_bump: bool,
) -> str:
    """Assemble the deterministic release-note shell around the generated body."""
    section = render_release_header(release_tag, published_at, image_number, source_repo)
    section += render_breaking_section(
        breaking_bullets,
        force_placeholder=force_breaking_placeholder,
        is_major_bump=is_major_bump,
    )
    body_clean = body.strip()
    if body_clean:
        section += body_clean + "\n\n"
    section += render_release_footer(source_repo, release_url)
    return section.rstrip() + "\n"

def update_markdown_file(md_path: Path, new_section: str) -> None:
    content = md_path.read_text()
    frontmatter = ""
    body = content
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            end += len("\n---")
            frontmatter = content[:end].rstrip("\n")
            body = content[end:].lstrip("\n")
    insertion = new_section.strip() + "\n\n"
    if "## " in body:
        idx = body.index("## ")
        updated_body = body[:idx] + insertion + body[idx:]
    else:
        updated_body = insertion + body
    updated_content = f"{frontmatter}\n\n{updated_body}".lstrip("\n") if frontmatter else updated_body
    md_path.write_text(updated_content.rstrip() + "\n")

