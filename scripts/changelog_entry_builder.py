#!/usr/bin/env python3
from __future__ import annotations

from typing import Any, Dict, List

from slugify import slugify

try:
    from scripts.changelog_config import (
        LABEL_MAPPING,
        PLACEHOLDER_DOCS_URL,
        PLACEHOLDER_LEARN_MORE_URL,
        REPO_CONFIG,
    )
    from scripts.changelog_llm_outputs import ChangelogLabel, GroupedChangelogOutput
    from scripts.changelog_validators import validate_grouped_changelog_output
except ModuleNotFoundError:  # pragma: no cover
    from changelog_config import (  # type: ignore[no-redef]
        LABEL_MAPPING,
        PLACEHOLDER_DOCS_URL,
        PLACEHOLDER_LEARN_MORE_URL,
        REPO_CONFIG,
    )
    from changelog_llm_outputs import ChangelogLabel, GroupedChangelogOutput  # type: ignore[no-redef]
    from changelog_validators import validate_grouped_changelog_output  # type: ignore[no-redef]

def slugify_title(title: str) -> str:
    return slugify(title)

def map_labels(pr_labels: List[str], suggested: List[ChangelogLabel]) -> List[str]:
    mapped = []
    for label in pr_labels:
        mapped_label = LABEL_MAPPING.get(label.lower())
        if mapped_label:
            mapped.append(mapped_label)
    if not mapped and suggested:
        mapped = [label.value for label in suggested]
    if not mapped:
        mapped = ["improvement"]
    return sorted(set(mapped))

def build_grouped_changelog_entries(
    grouped_output: GroupedChangelogOutput,
    prs: List[Dict[str, Any]],
    source_repo: str,
    published_at: str,
    starting_id: int,
) -> List[Dict[str, Any]]:
    """Convert grouped LLM output into schema-compliant changelog entries."""
    validate_grouped_changelog_output(grouped_output=grouped_output, prs=prs)

    pr_by_number: Dict[int, Dict[str, Any]] = {pr["number"]: pr for pr in prs}
    config = REPO_CONFIG[source_repo]
    entries: List[Dict[str, Any]] = []
    group_count = len(grouped_output.entries)
    base_id = starting_id - 1

    for index, entry in enumerate(grouped_output.entries):
        aggregate_labels: List[str] = []
        for pr_number in entry.pr_numbers:
            aggregate_labels.extend(pr_by_number[pr_number].get("labels", []))
        labels = map_labels(aggregate_labels, entry.suggested_labels)

        # Assign IDs so that the first group gets the highest ID, preserving LLM order
        # when new entries are later sorted in descending ID order.
        entry_id = base_id + (group_count - index)

        entries.append(
            {
                "id": entry_id,
                "slug": slugify_title(entry.title),
                "title": entry.title,
                "description": entry.description,
                "published_at": published_at,
                "published": True,
                "audience": config["audience"],
                "labels": labels,
                # Optional fields below - replace placeholders as needed
                "feature_image_url": "",
                "video_url": "",
                "learn_more_url": PLACEHOLDER_LEARN_MORE_URL,
                "docs_url": PLACEHOLDER_DOCS_URL,
                "should_highlight": False,
            }
        )

    return entries

