#!/usr/bin/env python3
from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from scripts.changelog_llm_outputs import (
        LLM_CALL_BREAKING_CHANGES,
        LLM_CALL_GROUPED_CHANGELOG_ENTRIES,
        LLM_CALL_RELEASE_NOTES_BODY,
        BreakingChangesOutput,
        GroupedChangelogOutput,
        MarkdownSection,
    )
    from scripts.changelog_llm_providers import StructuredLLMClient
    from scripts.changelog_prompts import (
        build_breaking_changes_prompt,
        build_grouped_changelog_entries_prompt,
        build_release_notes_body_prompt,
    )
    from scripts.changelog_validators import (
        validate_breaking_changes_output,
        validate_release_notes_body_output,
    )
except ModuleNotFoundError:  # pragma: no cover
    from changelog_llm_outputs import (  # type: ignore[no-redef]
        LLM_CALL_BREAKING_CHANGES,
        LLM_CALL_GROUPED_CHANGELOG_ENTRIES,
        LLM_CALL_RELEASE_NOTES_BODY,
        BreakingChangesOutput,
        GroupedChangelogOutput,
        MarkdownSection,
    )
    from changelog_llm_providers import StructuredLLMClient  # type: ignore[no-redef]
    from changelog_prompts import (  # type: ignore[no-redef]
        build_breaking_changes_prompt,
        build_grouped_changelog_entries_prompt,
        build_release_notes_body_prompt,
    )
    from changelog_validators import (  # type: ignore[no-redef]
        validate_breaking_changes_output,
        validate_release_notes_body_output,
    )


def generate_grouped_changelog_output(
    *,
    client: StructuredLLMClient,
    prs: List[Dict[str, Any]],
    source_repo: str,
    retry_feedback: Optional[str] = None,
) -> GroupedChangelogOutput:
    """Generate grouped changelog structured output with an explicit client."""
    if not prs:
        raise RuntimeError("No PRs provided to generate_grouped_changelog_output")
    prompt = build_grouped_changelog_entries_prompt(prs, source_repo, retry_feedback)
    return client.parse_structured_output(
        prompt=prompt,
        output_model=GroupedChangelogOutput,
        max_output_tokens=1200,
        call_name=LLM_CALL_GROUPED_CHANGELOG_ENTRIES,
    )


def generate_breaking_changes_output(
    *,
    client: StructuredLLMClient,
    breaking_prs: List[Dict[str, Any]],
    source_repo: str,
    include_pr_links: bool,
) -> tuple[BreakingChangesOutput, list[str]]:
    """Generate and validate breaking-change bullets with an explicit client."""
    if not breaking_prs:
        return BreakingChangesOutput(bullets=[]), []
    prompt = build_breaking_changes_prompt(breaking_prs, source_repo, include_pr_links)
    output = client.parse_structured_output(
        prompt=prompt,
        output_model=BreakingChangesOutput,
        max_output_tokens=900,
        call_name=LLM_CALL_BREAKING_CHANGES,
    )
    warnings = validate_breaking_changes_output(
        bullets=output.bullets,
        breaking_prs=breaking_prs,
        include_pr_links=include_pr_links,
    )
    return output, warnings


def generate_release_notes_body_output(
    *,
    client: StructuredLLMClient,
    prs: List[Dict[str, Any]],
    source_repo: str,
    include_pr_links: bool,
) -> tuple[MarkdownSection, list[str]]:
    """Generate and validate release-note body markdown with an explicit client."""
    if not prs:
        return MarkdownSection(content=""), []
    prompt = build_release_notes_body_prompt(prs, source_repo, include_pr_links)
    output = client.parse_structured_output(
        prompt=prompt,
        output_model=MarkdownSection,
        max_output_tokens=1800,
        call_name=LLM_CALL_RELEASE_NOTES_BODY,
    )
    warnings = validate_release_notes_body_output(
        body=output.content,
        prs=prs,
        include_pr_links=include_pr_links,
    )
    return output, warnings
