from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import changelog_validators as validators
from scripts.changelog_llm_providers import LLMOutputValidationError


def make_pr(number: int, labels: list[str] | None = None, repo: str = "zenml-io/zenml") -> dict[str, Any]:
    return {
        "number": number,
        "title": f"PR {number}",
        "labels": labels or ["release-notes"],
        "url": f"https://github.com/{repo}/pull/{number}",
        "body": f"Body for PR {number}",
        "repo": repo,
    }


def test_release_notes_body_validator_accepts_oss_body_with_required_links() -> None:
    prs = [make_pr(101), make_pr(102, labels=["bugfix"])]
    body = (
        "#### Better pipelines\n\n"
        "Pipeline authoring improved in [PR #101](https://github.com/zenml-io/zenml/pull/101).\n\n"
        "<details><summary>Fixed</summary>\n\n"
        "A bug was fixed in [PR #102](https://github.com/zenml-io/zenml/pull/102).\n"
        "</details>"
    )

    assert validators.validate_release_notes_body_output(
        body=body,
        prs=prs,
        include_pr_links=True,
    ) == []


@pytest.mark.parametrize(
    "body, expected",
    [
        ("## 0.85.0 (2026-06-02)", "must not include the deterministic `##` release header"),
        ('<img src="example.jpg">', "must not include the deterministic image tag"),
        ("### Breaking Changes", "must not include a Breaking Changes heading"),
        ("[View full release on GitHub](https://example.test)", "must not include the deterministic release footer link"),
        ("***", r"must not include the deterministic `\*\*\*` footer"),
    ],
)
def test_release_notes_body_validator_rejects_deterministic_sections(body: str, expected: str) -> None:
    with pytest.raises(LLMOutputValidationError, match=expected):
        validators.validate_release_notes_body_output(
            body=body,
            prs=[],
            include_pr_links=True,
        )


def test_release_notes_body_validator_requires_oss_pr_links() -> None:
    prs = [make_pr(101), make_pr(102)]
    body = "#### Updates\n\nPR 101 is described, but without the required markdown links."

    with pytest.raises(LLMOutputValidationError) as exc_info:
        validators.validate_release_notes_body_output(
            body=body,
            prs=prs,
            include_pr_links=True,
        )

    assert "#101" in str(exc_info.value)
    assert "#102" in str(exc_info.value)


@pytest.mark.parametrize(
    "body",
    [
        "#### Updates\n\nImproved a workflow in PR 8.",
        "#### Updates\n\nImproved a workflow in PR #8.",
        "#### Updates\n\nImproved a workflow in #8.",
        "#### Updates\n\nImproved a workflow in [PR #8](https://github.com/zenml-io/zenml-cloud-api/pull/8).",
        "#### Updates\n\nImproved a workflow in https://github.com/zenml-io/zenml-cloud-api/pull/8.",
    ],
)
def test_release_notes_body_validator_rejects_pro_pr_references(body: str) -> None:
    prs = [make_pr(8, repo="zenml-io/zenml-cloud-api")]

    with pytest.raises(LLMOutputValidationError, match="must not include PR links"):
        validators.validate_release_notes_body_output(
            body=body,
            prs=prs,
            include_pr_links=False,
        )


def test_release_notes_body_validator_accepts_split_line_fixed_details_block() -> None:
    prs = [make_pr(101, labels=["bugfix"])]
    body = (
        "#### Fixes\n\n"
        "<details>\n"
        "<summary>Fixed</summary>\n\n"
        "Fixed an issue in [PR #101](https://github.com/zenml-io/zenml/pull/101).\n"
        "</details>"
    )

    assert validators.validate_release_notes_body_output(
        body=body,
        prs=prs,
        include_pr_links=True,
    ) == []


def test_release_notes_body_validator_warns_for_bugfix_without_fixed_block() -> None:
    prs = [make_pr(101, labels=["bugfix"])]
    body = "#### Fixes\n\nFixed an issue in [PR #101](https://github.com/zenml-io/zenml/pull/101)."

    warnings = validators.validate_release_notes_body_output(
        body=body,
        prs=prs,
        include_pr_links=True,
    )

    assert warnings == ["Bugfix PRs exist, but the release-note body has no Fixed details block."]


def test_breaking_changes_validator_accepts_oss_bullets_with_links() -> None:
    prs = [make_pr(201, labels=["breaking-change"])]

    assert validators.validate_breaking_changes_output(
        bullets=["Update your pipeline code after the API rename in [PR #201](https://github.com/zenml-io/zenml/pull/201)."],
        breaking_prs=prs,
        include_pr_links=True,
    ) == []


def test_breaking_changes_validator_rejects_preformatted_bullets() -> None:
    prs = [make_pr(201, labels=["breaking-change"])]

    with pytest.raises(LLMOutputValidationError, match="must not start"):
        validators.validate_breaking_changes_output(
            bullets=["- Update usage in [PR #201](https://github.com/zenml-io/zenml/pull/201)."],
            breaking_prs=prs,
            include_pr_links=True,
        )


def test_breaking_changes_validator_requires_oss_links() -> None:
    prs = [make_pr(201, labels=["breaking-change"])]

    with pytest.raises(LLMOutputValidationError, match="#201"):
        validators.validate_breaking_changes_output(
            bullets=["Update your imports after the API rename."],
            breaking_prs=prs,
            include_pr_links=True,
        )


def test_breaking_changes_validator_requires_link_on_each_oss_bullet() -> None:
    prs = [make_pr(201, labels=["breaking-change"])]

    with pytest.raises(LLMOutputValidationError, match="bullet 2 must include"):
        validators.validate_breaking_changes_output(
            bullets=[
                "Remove old behavior in [PR #201](https://github.com/zenml-io/zenml/pull/201).",
                "Update your client configuration before upgrading.",
            ],
            breaking_prs=prs,
            include_pr_links=True,
        )


@pytest.mark.parametrize(
    "bullet",
    [
        "Update your settings after PR 8.",
        "Update your settings after PR #8.",
        "Update your settings after #8.",
        "Update your settings after [PR #8](https://github.com/zenml-io/zenml-cloud-api/pull/8).",
        "Update your settings after https://github.com/zenml-io/zenml-cloud-api/pull/8.",
    ],
)
def test_breaking_changes_validator_rejects_pro_pr_references(bullet: str) -> None:
    prs = [make_pr(8, labels=["breaking-change"], repo="zenml-io/zenml-cloud-api")]

    with pytest.raises(LLMOutputValidationError, match="must not include PR links"):
        validators.validate_breaking_changes_output(
            bullets=[bullet],
            breaking_prs=prs,
            include_pr_links=False,
        )


def test_breaking_changes_validator_warns_without_action_language() -> None:
    prs = [make_pr(201, labels=["breaking-change"])]

    warnings = validators.validate_breaking_changes_output(
        bullets=["Behavior changed in [PR #201](https://github.com/zenml-io/zenml/pull/201)."],
        breaking_prs=prs,
        include_pr_links=True,
    )

    assert warnings == ["Breaking-change bullet 1 may need clearer migration/action language."]
