from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import changelog_llm_generation as generation
from scripts import changelog_llm_outputs as outputs
from scripts import changelog_validators as validators
from scripts.changelog_llm_providers import LLMOutputValidationError


class RecordingStructuredClient:
    def __init__(self, output: object) -> None:
        self.output = output
        self.calls: list[dict[str, Any]] = []

    def parse_structured_output(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.output


def test_release_notes_body_generation_uses_raised_output_cap() -> None:
    client = RecordingStructuredClient(outputs.MarkdownSection(content="Users can now manage runs more clearly."))

    generation.generate_release_notes_body_output(
        client=client,
        prs=[
            {
                "number": 123,
                "title": "Improve run management",
                "body": "Adds clearer run controls.",
                "labels": ["enhancement"],
                "url": "https://github.com/zenml-io/zenml/pull/123",
            }
        ],
        source_repo="zenml-io/zenml",
        include_pr_links=False,
    )

    assert client.calls[0]["max_output_tokens"] == 12000
    assert client.calls[0]["call_name"] == outputs.LLM_CALL_RELEASE_NOTES_BODY
    assert client.calls[0]["output_model"] == outputs.MarkdownSection


def make_breaking_pr() -> dict[str, Any]:
    return {
        "number": 456,
        "title": "Remove the per-pipeline runs endpoint",
        "body": "## Upgrade impact\nOlder clients that list runs per pipeline fail.",
        "labels": ["breaking-change"],
        "url": "https://github.com/zenml-io/zenml/pull/456",
        "repo": "zenml-io/zenml",
    }


def test_compatibility_generation_uses_its_own_call_and_author_notes() -> None:
    client = RecordingStructuredClient(
        outputs.CompatibilityAssessment(
            status=outputs.CompatibilityStatus.EXCEPTIONS,
            server_impact="Older clients can no longer list runs per pipeline.",
            client_upgrade_notes="",
            breaking_point_description="Listing runs per pipeline fails for older clients.",
        )
    )

    generation.generate_compatibility_output(
        client=client,
        release_tag="0.99.0",
        breaking_prs=[make_breaking_pr()],
        release_notes_prs=[],
        breaking_points="- none",
    )

    assert client.calls[0]["call_name"] == outputs.LLM_CALL_COMPATIBILITY
    assert client.calls[0]["max_output_tokens"] == 1200
    assert client.calls[0]["output_model"] == outputs.CompatibilityAssessment
    assert "Upgrade impact (written by the PR author): Older clients that list runs" in client.calls[0]["prompt"]


@pytest.mark.parametrize(
    ("status", "description", "message"),
    [
        (outputs.CompatibilityStatus.COMPATIBLE, "Something fails.", "must be empty when status is compatible"),
        (outputs.CompatibilityStatus.BREAKING, "", "is required when status is exceptions or breaking"),
    ],
)
def test_compatibility_generation_rejects_inconsistent_breaking_points(
    status: outputs.CompatibilityStatus,
    description: str,
    message: str,
) -> None:
    client = RecordingStructuredClient(
        outputs.CompatibilityAssessment(
            status=status,
            server_impact="Server impact.",
            client_upgrade_notes="",
            breaking_point_description=description,
        )
    )

    with pytest.raises(LLMOutputValidationError, match=message):
        generation.generate_compatibility_output(
            client=client,
            release_tag="0.99.0",
            breaking_prs=[make_breaking_pr()],
            release_notes_prs=[],
            breaking_points="- none",
        )


def test_compatibility_validator_rejects_pr_references() -> None:
    output = outputs.CompatibilityAssessment(
        status=outputs.CompatibilityStatus.EXCEPTIONS,
        server_impact="See https://github.com/zenml-io/zenml/pull/456 for details.",
        client_upgrade_notes="",
        breaking_point_description="Listing runs per pipeline fails for older clients.",
    )

    with pytest.raises(LLMOutputValidationError, match="must not include PR links"):
        validators.validate_compatibility_output(output=output, breaking_prs=[make_breaking_pr()])
