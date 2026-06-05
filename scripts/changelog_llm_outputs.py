#!/usr/bin/env python3
from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, ConfigDict, Field

class ChangelogLabel(str, Enum):
    BUGFIX = "bugfix"
    DEPRECATION = "deprecation"
    IMPROVEMENT = "improvement"
    FEATURE = "feature"

class Audience(str, Enum):
    PRO = "pro"
    OSS = "oss"
    ALL = "all"

LLM_CALL_CHANGELOG_COPY = "changelog_copy"

LLM_CALL_GROUPED_CHANGELOG_ENTRIES = "grouped_changelog_entries"

LLM_CALL_BREAKING_CHANGES = "breaking_changes"

LLM_CALL_RELEASE_NOTES_BODY = "release_notes_body"

LLM_CALL_MARKDOWN_SECTION = "markdown_section"

class StrictLLMOutput(BaseModel):
    """Base for model-produced structured outputs.

    OpenAI strict structured outputs require every field to be present and reject
    extra object keys, so the model-output schemas use explicit required lists
    instead of Pydantic defaults.
    """

    model_config = ConfigDict(extra="forbid")

class ChangelogCopy(StrictLLMOutput):
    title: str = Field(..., max_length=60, description="Clear, user-facing title without PR number")
    description: str = Field(..., description="1-3 sentences explaining the user-facing value, markdown allowed")
    suggested_labels: List[ChangelogLabel] = Field(..., description="Suggested labels based on the PR content; use [] when none apply")

class GroupedChangelogEntry(StrictLLMOutput):
    title: str = Field(
        ...,
        max_length=60,
        description="User-facing title for a group of related PRs, no PR numbers.",
    )
    description: str = Field(
        ...,
        description="1-3 sentences summarizing the grouped theme in user terms, markdown allowed.",
    )
    suggested_labels: List[ChangelogLabel] = Field(
        ...,
        description="Suggested labels based on all PRs in this group; use [] when none apply.",
    )
    pr_numbers: List[int] = Field(
        ...,
        min_length=1,
        description="List of PR numbers covered by this group.",
    )

class GroupedChangelogOutput(StrictLLMOutput):
    entries: List[GroupedChangelogEntry] = Field(
        ...,
        min_length=1,
        max_length=3,
        description="1-3 grouped changelog entries summarizing the release; 2-3 preferred when the number of PRs allows it.",
    )

class BreakingChangesOutput(StrictLLMOutput):
    bullets: List[str] = Field(
        ...,
        description="List of breaking change bullet points, one per significant breaking change; use [] when none apply.",
    )

class MarkdownSection(StrictLLMOutput):
    content: str = Field(..., description="Complete markdown section for the release notes")

