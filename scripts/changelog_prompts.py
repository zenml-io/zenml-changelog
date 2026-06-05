#!/usr/bin/env python3
from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from scripts.changelog_config import REPO_CONFIG
except ModuleNotFoundError:  # pragma: no cover
    from changelog_config import REPO_CONFIG  # type: ignore[no-redef]


def _audience_for_repo_type(repo_type: str) -> str:
    return "open source users" if repo_type == "oss" else "ZenML Pro users"


def _audience_for_source_repo(source_repo: str) -> str:
    return _audience_for_repo_type(REPO_CONFIG[source_repo]["type"])


def _single_line_body(pr: Dict[str, Any], max_chars: int) -> str:
    return (pr.get("body") or "")[:max_chars].replace(chr(10), " ")


def _labels_summary(pr: Dict[str, Any]) -> str:
    return ", ".join(pr.get("labels", [])) or "none"


def _detailed_pr_summary(pr: Dict[str, Any], *, body_chars: int) -> str:
    return (
        f"- #{pr['number']}: {pr['title']}\n"
        f"  Labels: {_labels_summary(pr)}\n"
        f"  URL: {pr['url']}\n"
        f"  Body (truncated): {_single_line_body(pr, body_chars)}"
    )


def _inline_pr_summary(pr: Dict[str, Any], *, body_chars: int, include_number_prefix: bool) -> str:
    prefix = f"{pr['title']} (#{pr['number']})" if include_number_prefix else pr["title"]
    return f"- {prefix}: {pr['url']} — {_single_line_body(pr, body_chars)}"


def build_changelog_copy_prompt(pr_title: str, pr_body: str, pr_url: str, repo_type: str) -> str:
    audience = _audience_for_repo_type(repo_type)
    return (
        "You are writing changelog entries for ZenML, an MLOps platform.\n\n"
        f"PR Title: {pr_title}\n"
        f"PR URL: {pr_url}\n"
        f"PR Body:\n{pr_body[:3500]}\n\n"
        f"The audience is {audience}. Focus on what users can now do or benefit from.\n"
        "Generate a concise title (max 60 characters, no PR number), a 1-3 sentence markdown-friendly "
        "description, and suggest appropriate labels. Always set `suggested_labels`; return [] when none apply. "
        "Feel free to include inline markdown links to well-known tools and libraries (e.g., "
        "[MLflow](https://github.com/mlflow/mlflow), [Transformers](https://github.com/huggingface/transformers)). "
        "Prefer linking to GitHub repos when available."
    )

def build_grouped_changelog_entries_prompt(
    prs: List[Dict[str, Any]],
    source_repo: str,
    retry_feedback: Optional[str] = None,
) -> str:
    audience = _audience_for_source_repo(source_repo)
    pr_summaries = "\n".join(_detailed_pr_summary(pr, body_chars=400) for pr in prs)

    prompt = (
        "You are helping write grouped changelog entries for ZenML, an MLOps platform.\n\n"
        "Here is the list of merged PRs with the `release-notes` label for this release. "
        "Each PR includes its number, title, labels, URL, and a truncated body:\n\n"
        f"{pr_summaries}\n\n"
        f"The audience is {audience}. Focus on what users can now do or benefit from.\n\n"
        "Your task:\n"
        "- Group these PRs into 2-3 thematic user-facing changelog entries when possible. "
        "For very small releases, 1 entry is acceptable.\n"
        "- Each entry should summarize a coherent theme or area of improvement.\n"
        "- Every PR must appear in exactly one group.\n"
        "- Do not include PR numbers in the titles or descriptions.\n"
        "- Use markdown-friendly prose in the descriptions (1-3 sentences).\n\n"
        "Output format rules:\n"
        "- Produce between 1 and 3 entries in total (2-3 preferred when the number of PRs allows it).\n"
        "- For each entry, set `title`, `description`, `suggested_labels`, and `pr_numbers`.\n"
        "- Each title MUST be at most 60 characters. Keep titles concise and punchy.\n"
        "- Titles should be short, generic, benefit-oriented dashboard-card titles.\n"
        "- Avoid over-specific titles that name one narrow implementation detail when the group covers a broader user benefit.\n"
        "- `pr_numbers` must be a list of the PR numbers from the list above that this entry covers.\n"
        "- Use `suggested_labels` based on the overall theme of the grouped PRs, using only: "
        "feature, improvement, bugfix, deprecation. Return [] if no label applies.\n"
        "Avoid low-level implementation details and emphasize user-facing value."
    )

    if retry_feedback:
        prompt += (
            "\n\nPrevious grouped output failed validation.\n\n"
            f"{retry_feedback}\n\n"
            "Generate the grouped changelog entries again. Every PR number from the input list "
            "must appear exactly once. Do not invent, duplicate, or omit PR numbers."
        )
    return prompt

def build_breaking_changes_prompt(
    breaking_prs: List[Dict[str, Any]],
    source_repo: str,
    include_pr_links: bool,
) -> str:
    audience = _audience_for_source_repo(source_repo)
    pr_summaries = "\n".join(_detailed_pr_summary(pr, body_chars=700) for pr in breaking_prs)
    link_instruction = (
        "Include a markdown link to the PR in each bullet using the exact format "
        "[PR #<number>](<url>). If you combine closely related breaking PRs into one bullet, "
        "include all relevant PR links in that bullet."
        if include_pr_links
        else "Do not include PR links, raw URLs, or PR numbers in the bullets; keep the prose concise."
    )
    return (
        "You are writing the \"Breaking Changes\" section for ZenML release notes.\n\n"
        f"Repository: {source_repo}\n"
        f"Audience: {audience}\n\n"
        "Here are PRs labeled as breaking changes for this release:\n\n"
        f"{pr_summaries}\n\n"
        "Task:\n"
        "- Write user-facing bullet point text summarizing what is breaking and how users should adapt.\n"
        "- Produce one bullet per breaking PR, unless a small grouping is clearly warranted.\n"
        f"- {link_instruction}\n"
        "- Each bullet must be plain text only and must NOT start with '-' or '*'. "
        "The caller will format bullets.\n"
        "- Always set `bullets`; if there is nothing meaningful to summarize, return an empty list.\n"
        "- Avoid implementation details; focus on behavioral changes, removals, renamed APIs, "
        "compatibility requirements, or required migration steps.\n"
    )

def build_release_notes_body_prompt(
    prs: List[Dict[str, Any]],
    source_repo: str,
    include_pr_links: bool,
) -> str:
    audience = _audience_for_source_repo(source_repo)
    pr_summaries = "\n".join(
        _inline_pr_summary(pr, body_chars=500, include_number_prefix=True) for pr in prs
    )
    include_links_instruction = (
        "Include a markdown link to every input PR using the exact format [PR #<number>](<url>)."
        if include_pr_links
        else "Do not include PR links, raw URLs, or PR numbers; keep the prose concise."
    )
    return (
        "You are writing the release notes body for ZenML.\n\n"
        f"Repository: {source_repo}\n"
        f"Audience: {audience}\n\n"
        "Merged PRs to cover (release-notes label):\n"
        f"{pr_summaries}\n\n"
        "Output rules (CRITICAL):\n"
        "- Output markdown for the body only.\n"
        "- Do NOT include the `## <release_tag>` header (the caller will render the release header).\n"
        "- Do NOT include the `<img>` tag.\n"
        "- Do NOT include a \"Breaking Changes\" heading.\n"
        "- Do NOT include the footer, any release link section, or `***`.\n\n"
        "Formatting requirements:\n"
        "- Use `####` subsection headers to group related changes by theme.\n"
        "- Prefer a short framing sentence under each subsection, followed by bullet points for concrete specifics.\n"
        "- Use bullets for detailed changes, examples, and fixes instead of dense paragraphs.\n"
        "- Use `<details><summary>Fixed</summary>...</details>` for bug fixes.\n"
        f"- {include_links_instruction}\n\n"
        "Writing guidance:\n"
        "- Highlight the most user-facing improvements first.\n"
        "- Avoid low-level implementation details; focus on what users can now do.\n"
        "- Keep sections clear, readable, and scannable.\n"
    )

def build_markdown_section_prompt(
    prs: List[Dict[str, Any]],
    release_tag: str,
    release_url: str,
    published_at: str,
    source_repo: str,
    image_number: int,
) -> str:
    config = REPO_CONFIG[source_repo]
    repo_type = config["type"]
    pr_summaries = "\n".join(
        _inline_pr_summary(pr, body_chars=300, include_number_prefix=True) for pr in prs
    )
    include_links_instruction = (
        "Include a markdown link to each PR using the format [PR #<number>](<url>) for each bullet."
        if repo_type == "oss"
        else "Do not include PR links, raw URLs, or PR numbers; keep the prose concise for Pro audiences."
    )
    footer_parts: List[str] = []
    if config.get("include_release_link"):
        footer_parts.append(f"[View full release on GitHub]({release_url})")
    if config.get("include_compatibility_note"):
        footer_parts.append("> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.")
    if footer_parts:
        footer_instruction = "Append at the end:\n" + "\n\n".join(footer_parts) + "\n\n***"
    else:
        footer_instruction = "End the section with *** on its own line."
    return (
        f"Write release notes for repository {source_repo} version {release_tag}.\n"
        f"Release URL: {release_url}\n"
        f"Published at: {published_at}\n\n"
        "PRs with the release-notes label:\n"
        f"{pr_summaries}\n\n"
        "Generate a markdown section with this structure:\n"
        f"## {release_tag} ({published_at[:10]})\n\n"
        f"See what's new and improved in version {release_tag}.\n\n"
        f'<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/{image_number}.jpg" '
        f'align="left" alt="ZenML {release_tag}" width="800">\n\n'
        "Use bolded subsection headers (####) to group related changes. "
        "Use <details><summary>Fixed</summary>...</details> for bug fixes and "
        "<details><summary>Improved</summary>...</details> for minor improvements when appropriate. "
        f"{include_links_instruction} "
        "Feel free to include inline markdown links to well-known tools and libraries (e.g., "
        "[MLflow](https://github.com/mlflow/mlflow), [Transformers](https://github.com/huggingface/transformers)). "
        "Prefer linking to GitHub repos when available. "
        "Highlight the top user-facing improvements first. "
        f"{footer_instruction}"
    )

