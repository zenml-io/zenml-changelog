#!/usr/bin/env python3
from __future__ import annotations

import re
from typing import Any, Dict, List

try:
    from scripts.changelog_llm_outputs import GroupedChangelogOutput
    from scripts.changelog_llm_providers import LLMOutputValidationError
except ModuleNotFoundError:  # pragma: no cover
    from changelog_llm_outputs import GroupedChangelogOutput  # type: ignore[no-redef]
    from changelog_llm_providers import LLMOutputValidationError  # type: ignore[no-redef]

class GroupedChangelogSemanticError(RuntimeError):
    """Recoverable semantic validation failure for grouped changelog output."""

    def __init__(self, details: List[str], invalid_grouping_summary: str) -> None:
        self.details = details
        self.invalid_grouping_summary = invalid_grouping_summary
        message = "\n".join(f"- {detail}" for detail in details)
        super().__init__(message)

def markdown_pr_link_pattern(pr: Dict[str, Any]) -> str:
    number = int(pr["number"])
    url = re.escape(str(pr.get("url", "")))
    return rf"\[PR #{number}\]\({url}\)"

def missing_markdown_pr_links(text: str, prs: List[Dict[str, Any]]) -> List[int]:
    missing: List[int] = []
    for pr in prs:
        if not re.search(markdown_pr_link_pattern(pr), text):
            missing.append(int(pr["number"]))
    return missing

def contains_forbidden_pr_reference(text: str, prs: List[Dict[str, Any]]) -> bool:
    if re.search(r"https://github\.com/[^\s)]+/pull/\d+", text):
        return True
    for pr in prs:
        number = int(pr["number"])
        if re.search(rf"\[[^\]]*(?:PR\s*#?\s*{number}|#{number})[^\]]*\]\([^)]*\)", text, flags=re.IGNORECASE):
            return True
        if re.search(rf"\bPR\s*#?\s*{number}\b", text, flags=re.IGNORECASE):
            return True
        if re.search(rf"(?<![\w/])#{number}\b", text):
            return True
    return False

def validate_release_notes_body_output(
    *,
    body: str,
    prs: List[Dict[str, Any]],
    include_pr_links: bool,
) -> List[str]:
    """Validate model-generated release-note body before deterministic assembly."""
    details: List[str] = []
    warnings: List[str] = []
    lines = body.splitlines()

    if any(line.startswith("## ") for line in lines):
        details.append("Release-note body must not include the deterministic `##` release header.")
    if re.search(r"<\s*img\b", body, flags=re.IGNORECASE):
        details.append("Release-note body must not include the deterministic image tag.")
    if re.search(r"^#+\s+Breaking Changes\b", body, flags=re.IGNORECASE | re.MULTILINE):
        details.append("Release-note body must not include a Breaking Changes heading.")
    if "[View full release on GitHub]" in body:
        details.append("Release-note body must not include the deterministic release footer link.")
    if any(line.strip() == "***" for line in lines):
        details.append("Release-note body must not include the deterministic `***` footer.")

    if prs and include_pr_links:
        missing = missing_markdown_pr_links(body, prs)
        if missing:
            missing_str = ", ".join(f"#{number}" for number in missing)
            details.append(f"Release-note body is missing required PR links for: {missing_str}.")
    if not include_pr_links and contains_forbidden_pr_reference(body, prs):
        details.append("Release-note body must not include PR links, raw PR URLs, or PR numbers for this audience.")

    has_bugfix_prs = any(
        any(label.lower() in {"bug", "bugfix", "fix"} for label in pr.get("labels", []))
        for pr in prs
    )
    has_fixed_details_block = re.search(
        r"<details>\s*<summary>\s*Fixed\s*</summary>",
        body,
        flags=re.IGNORECASE,
    )
    if has_bugfix_prs and not has_fixed_details_block:
        warnings.append("Bugfix PRs exist, but the release-note body has no Fixed details block.")

    if details:
        raise LLMOutputValidationError(details)
    return warnings

def validate_breaking_changes_output(
    *,
    bullets: List[str],
    breaking_prs: List[Dict[str, Any]],
    include_pr_links: bool,
) -> List[str]:
    """Validate model-generated breaking-change bullets before formatting."""
    details: List[str] = []
    warnings: List[str] = []
    combined = "\n".join(bullets)

    for index, bullet in enumerate(bullets, start=1):
        stripped = bullet.strip()
        if stripped.startswith(("-", "*")):
            details.append(f"Breaking-change bullet {index} must not start with '-' or '*'.")
        if stripped and not re.search(
            r"\b(rename|remove|update|migrate|configure|replace|requires|no longer)\b",
            stripped,
            flags=re.IGNORECASE,
        ):
            warnings.append(
                f"Breaking-change bullet {index} may need clearer migration/action language."
            )

    if breaking_prs and include_pr_links:
        for index, bullet in enumerate(bullets, start=1):
            if not re.search(r"\[PR #\d+\]\([^)]*\)", bullet):
                details.append(f"Breaking-change bullet {index} must include a markdown PR link.")
        missing = missing_markdown_pr_links(combined, breaking_prs)
        if missing:
            missing_str = ", ".join(f"#{number}" for number in missing)
            details.append(f"Breaking-change bullets are missing required PR links for: {missing_str}.")
    if not include_pr_links and contains_forbidden_pr_reference(combined, breaking_prs):
        details.append("Breaking-change bullets must not include PR links, raw PR URLs, or PR numbers for this audience.")

    if details:
        raise LLMOutputValidationError(details)
    return warnings

def format_repo_qualified_pr(pr: Dict[str, Any]) -> str:
    """Return a compact repo-qualified PR identifier for hard validation errors."""
    repo = pr.get("repo") or "<unknown repo>"
    return f"{repo}#{pr['number']}"

def assert_unique_grouped_pr_numbers(prs: List[Dict[str, Any]]) -> None:
    """Fail fast when bare PR numbers cannot uniquely identify grouped PRs."""
    prs_by_number: Dict[int, List[Dict[str, Any]]] = {}
    for pr in prs:
        prs_by_number.setdefault(pr["number"], []).append(pr)

    ambiguous_groups = {
        number: grouped_prs
        for number, grouped_prs in prs_by_number.items()
        if len(grouped_prs) > 1
    }
    if not ambiguous_groups:
        return

    examples = []
    for number, grouped_prs in sorted(ambiguous_groups.items()):
        repo_qualified = ", ".join(format_repo_qualified_pr(pr) for pr in grouped_prs)
        examples.append(f"PR #{number}: {repo_qualified}")

    raise RuntimeError(
        "Cannot generate grouped changelog entries because multiple source PRs share "
        "the same PR number. The current grouped-output format only returns bare "
        "PR numbers, so these inputs would be ambiguous. Conflicting PR records: "
        + "; ".join(examples)
    )

def summarize_grouped_changelog_output(grouped_output: GroupedChangelogOutput) -> str:
    """Return compact group titles and PR numbers for retry feedback."""
    if not grouped_output.entries:
        return "- <no grouped entries>: []"

    return "\n".join(
        f"- {entry.title}: [{', '.join(str(number) for number in entry.pr_numbers)}]"
        for entry in grouped_output.entries
    )

def validate_grouped_changelog_output(
    grouped_output: GroupedChangelogOutput,
    prs: List[Dict[str, Any]],
) -> None:
    """Validate that grouped changelog output assigns each input PR exactly once."""
    assert_unique_grouped_pr_numbers(prs)

    known_numbers = {pr["number"] for pr in prs}
    assigned_counts: Dict[int, int] = {}
    details: List[str] = []

    for entry in grouped_output.entries:
        for pr_number in entry.pr_numbers:
            assigned_counts[pr_number] = assigned_counts.get(pr_number, 0) + 1
            if pr_number not in known_numbers:
                details.append(
                    f"Grouped changelog entry '{entry.title}' references unknown PR #{pr_number}."
                )

    for pr_number, count in sorted(assigned_counts.items()):
        if count > 1:
            details.append(
                f"PR #{pr_number} appears in more than one grouped changelog entry."
            )

    missing_numbers = known_numbers - set(assigned_counts.keys())
    if missing_numbers:
        missing_str = ", ".join(f"#{number}" for number in sorted(missing_numbers))
        details.append(
            f"The following PRs were not assigned to any grouped changelog entry: {missing_str}."
        )

    if details:
        raise GroupedChangelogSemanticError(
            details=details,
            invalid_grouping_summary=summarize_grouped_changelog_output(grouped_output),
        )

def build_grouped_retry_feedback(error: GroupedChangelogSemanticError) -> str:
    """Build compact validation feedback for a semantic grouped-output retry."""
    validation_feedback = "\n".join(f"- {detail}" for detail in error.details)
    return (
        "Validation feedback:\n"
        f"{validation_feedback}\n\n"
        "Previous invalid grouping:\n"
        f"{error.invalid_grouping_summary}"
    )

def format_grouped_attempt_summaries(attempt_errors: List[GroupedChangelogSemanticError]) -> str:
    """Format semantic retry failures for the final actionable error."""
    return "\n\n".join(
        f"Attempt {index}:\n" + "\n".join(f"- {detail}" for detail in error.details)
        for index, error in enumerate(attempt_errors, start=1)
    )

