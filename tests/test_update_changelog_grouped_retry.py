from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import changelog_entry_builder as entry_builder
from scripts import changelog_validators as validators
from scripts import update_changelog as uc
from scripts.changelog_llm_outputs import ChangelogLabel, GroupedChangelogEntry, GroupedChangelogOutput


def make_pr(
    number: int,
    labels: list[str] | None = None,
    repo: str = "zenml-io/zenml",
) -> dict[str, Any]:
    return {
        "number": number,
        "title": f"PR {number}",
        "labels": labels or [],
        "url": f"https://github.com/{repo}/pull/{number}",
        "body": f"Release-note body for PR {number}",
        "repo": repo,
    }


def make_entry(
    title: str,
    pr_numbers: list[int],
    suggested_labels: list[ChangelogLabel] | None = None,
) -> GroupedChangelogEntry:
    return GroupedChangelogEntry(
        title=title,
        description=f"Description for {title}",
        suggested_labels=suggested_labels or [],
        pr_numbers=pr_numbers,
    )


def make_output(entries: list[GroupedChangelogEntry]) -> GroupedChangelogOutput:
    return GroupedChangelogOutput(entries=entries)


def sample_prs() -> list[dict[str, Any]]:
    return [
        make_pr(101, ["feature"]),
        make_pr(102, ["enhancement"]),
        make_pr(103, []),
    ]


def test_duplicate_pr_numbers_raise_semantic_error() -> None:
    grouped_output = make_output(
        [
            make_entry("Better pipelines", [101, 102]),
            make_entry("More fixes", [101, 103]),
        ]
    )

    with pytest.raises(validators.GroupedChangelogSemanticError) as exc_info:
        validators.validate_grouped_changelog_output(grouped_output, sample_prs())

    error = exc_info.value
    assert "PR #101 appears in more than one grouped changelog entry" in str(error)
    assert "- Better pipelines: [101, 102]" in error.invalid_grouping_summary
    assert "- More fixes: [101, 103]" in error.invalid_grouping_summary


def test_unknown_pr_numbers_raise_semantic_error() -> None:
    grouped_output = make_output(
        [
            make_entry("Better pipelines", [101, 102]),
            make_entry("Invented item", [103, 9999]),
        ]
    )

    with pytest.raises(validators.GroupedChangelogSemanticError) as exc_info:
        validators.validate_grouped_changelog_output(grouped_output, sample_prs())

    assert "references unknown PR #9999" in str(exc_info.value)


def test_missing_pr_numbers_raise_semantic_error() -> None:
    grouped_output = make_output([make_entry("Better pipelines", [101, 102])])

    with pytest.raises(validators.GroupedChangelogSemanticError) as exc_info:
        validators.validate_grouped_changelog_output(grouped_output, sample_prs())

    assert "#103" in str(exc_info.value)
    assert "not assigned to any grouped changelog entry" in str(exc_info.value)


def test_valid_grouped_output_preserves_conversion_behavior() -> None:
    grouped_output = make_output(
        [
            make_entry("Better pipelines", [101, 102], [ChangelogLabel.BUGFIX]),
            make_entry("Cleaner metadata", [103], [ChangelogLabel.BUGFIX]),
        ]
    )

    entries = entry_builder.build_grouped_changelog_entries(
        grouped_output=grouped_output,
        prs=sample_prs(),
        source_repo="zenml-io/zenml",
        published_at="2026-05-12T10:00:00Z",
        starting_id=100,
    )

    assert [entry["id"] for entry in entries] == [101, 100]
    assert [entry["slug"] for entry in entries] == ["better-pipelines", "cleaner-metadata"]
    assert [entry["title"] for entry in entries] == ["Better pipelines", "Cleaner metadata"]
    assert [entry["audience"] for entry in entries] == ["oss", "oss"]
    assert [entry["labels"] for entry in entries] == [["feature", "improvement"], ["bugfix"]]
    assert all(entry["published_at"] == "2026-05-12T10:00:00Z" for entry in entries)
    assert all(entry["published"] is True for entry in entries)


def test_semantic_retry_succeeds_on_second_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str | None] = []
    invalid_output = make_output(
        [
            make_entry("Duplicate", [101, 102]),
            make_entry("Duplicate again", [101, 103]),
        ]
    )
    valid_output = make_output(
        [
            make_entry("Better pipelines", [101, 102]),
            make_entry("Cleaner metadata", [103]),
        ]
    )

    def fake_llm_generate_grouped_changelog_entries(
        prs: list[dict[str, Any]],
        source_repo: str,
        retry_feedback: str | None = None,
    ) -> GroupedChangelogOutput:
        calls.append(retry_feedback)
        return invalid_output if len(calls) == 1 else valid_output

    monkeypatch.setattr(
        uc,
        "llm_generate_grouped_changelog_entries",
        fake_llm_generate_grouped_changelog_entries,
    )

    entries = uc.generate_valid_grouped_changelog_entries(
        prs=sample_prs(),
        source_repo="zenml-io/zenml",
        published_at="2026-05-12T10:00:00Z",
        starting_id=100,
    )

    assert [entry["title"] for entry in entries] == ["Better pipelines", "Cleaner metadata"]
    assert calls[0] is None
    assert calls[1]
    assert "Validation feedback:" in calls[1]
    assert "Previous invalid grouping:" in calls[1]
    assert "PR #101 appears in more than one grouped changelog entry" in calls[1]


def test_retry_exhaustion_fails_after_three_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str | None] = []
    invalid_output = make_output(
        [
            make_entry("Duplicate", [101, 102]),
            make_entry("Duplicate again", [101, 103]),
        ]
    )

    def fake_llm_generate_grouped_changelog_entries(
        prs: list[dict[str, Any]],
        source_repo: str,
        retry_feedback: str | None = None,
    ) -> GroupedChangelogOutput:
        calls.append(retry_feedback)
        return invalid_output

    monkeypatch.setattr(
        uc,
        "llm_generate_grouped_changelog_entries",
        fake_llm_generate_grouped_changelog_entries,
    )

    with pytest.raises(RuntimeError) as exc_info:
        uc.generate_valid_grouped_changelog_entries(
            prs=sample_prs(),
            source_repo="zenml-io/zenml",
            published_at="2026-05-12T10:00:00Z",
            starting_id=100,
        )

    message = str(exc_info.value)
    assert len(calls) == 3
    assert "after 3 attempts" in message
    assert "Attempt 1:" in message
    assert "Attempt 2:" in message
    assert "Attempt 3:" in message
    assert "No changelog.json, markdown, or .image_state updates were written." in message


def test_non_semantic_errors_are_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_llm_generate_grouped_changelog_entries(
        prs: list[dict[str, Any]],
        source_repo: str,
        retry_feedback: str | None = None,
    ) -> GroupedChangelogOutput:
        raise RuntimeError("Anthropic client not initialized")

    monkeypatch.setattr(
        uc,
        "llm_generate_grouped_changelog_entries",
        fake_llm_generate_grouped_changelog_entries,
    )

    with pytest.raises(RuntimeError, match="Anthropic client not initialized"):
        uc.generate_valid_grouped_changelog_entries(
            prs=sample_prs(),
            source_repo="zenml-io/zenml",
            published_at="2026-05-12T10:00:00Z",
            starting_id=100,
        )


def test_duplicate_input_pr_numbers_fail_before_llm_without_semantic_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_calls = 0

    def fake_llm_generate_grouped_changelog_entries(
        prs: list[dict[str, Any]],
        source_repo: str,
        retry_feedback: str | None = None,
    ) -> GroupedChangelogOutput:
        nonlocal llm_calls
        llm_calls += 1
        return make_output([make_entry("Ambiguous", [101])])

    monkeypatch.setattr(
        uc,
        "llm_generate_grouped_changelog_entries",
        fake_llm_generate_grouped_changelog_entries,
    )
    ambiguous_prs = [
        make_pr(101, repo="zenml-io/zenml"),
        make_pr(101, repo="zenml-io/zenml-dashboard"),
    ]

    with pytest.raises(RuntimeError) as exc_info:
        uc.generate_valid_grouped_changelog_entries(
            prs=ambiguous_prs,
            source_repo="zenml-io/zenml",
            published_at="2026-05-12T10:00:00Z",
            starting_id=100,
        )

    error = exc_info.value
    assert not isinstance(error, validators.GroupedChangelogSemanticError)
    assert llm_calls == 0
    assert "multiple source PRs share the same PR number" in str(error)
    assert "grouped-output format only returns bare PR numbers" in str(error)
    assert "zenml-io/zenml#101" in str(error)
    assert "zenml-io/zenml-dashboard#101" in str(error)

    with pytest.raises(RuntimeError, match="multiple source PRs share the same PR number"):
        entry_builder.build_grouped_changelog_entries(
            grouped_output=make_output([make_entry("Ambiguous", [101])]),
            prs=ambiguous_prs,
            source_repo="zenml-io/zenml",
            published_at="2026-05-12T10:00:00Z",
            starting_id=100,
        )
