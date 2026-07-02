from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import changelog_llm_generation as generation
from scripts import changelog_llm_outputs as outputs


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

    assert client.calls[0]["max_output_tokens"] == 6000
    assert client.calls[0]["call_name"] == outputs.LLM_CALL_RELEASE_NOTES_BODY
    assert client.calls[0]["output_model"] == outputs.MarkdownSection
