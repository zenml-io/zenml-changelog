from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import changelog_llm_outputs as outputs
from scripts import changelog_llm_providers as providers


class FakeAnthropicMessages:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] | None = None

    def parse(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return SimpleNamespace(
            parsed_output=outputs.ChangelogCopy(
                title="A useful update",
                description="Users can do something useful.",
                suggested_labels=[],
            )
        )


class FakeAnthropicClient:
    def __init__(self) -> None:
        self.messages = FakeAnthropicMessages()
        self.beta = SimpleNamespace(messages=self.messages)


class FakeOpenAIResponses:
    def __init__(
        self,
        parsed: object | None,
        *,
        status: str = "completed",
        output: list[object] | None = None,
        incomplete_details: object | None = None,
    ) -> None:
        self.parsed = parsed
        self.status = status
        self.output = output or []
        self.incomplete_details = incomplete_details
        self.kwargs: dict[str, Any] | None = None

    def parse(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return SimpleNamespace(
            output_parsed=self.parsed,
            status=self.status,
            output=self.output,
            incomplete_details=self.incomplete_details,
        )


class FakeOpenAIClient:
    def __init__(
        self,
        parsed: object | None,
        *,
        status: str = "completed",
        output: list[object] | None = None,
        incomplete_details: object | None = None,
    ) -> None:
        self.responses = FakeOpenAIResponses(
            parsed,
            status=status,
            output=output,
            incomplete_details=incomplete_details,
        )


def test_anthropic_structured_client_maps_common_parse_arguments() -> None:
    fake = FakeAnthropicClient()
    client = providers.AnthropicStructuredLLMClient(fake, model="claude-test")  # type: ignore[arg-type]

    result = client.parse_structured_output(
        prompt="Write copy",
        output_model=outputs.ChangelogCopy,
        max_output_tokens=123,
        call_name="copy",
    )

    assert result.title == "A useful update"
    assert fake.messages.kwargs == {
        "model": "claude-test",
        "betas": ["structured-outputs-2025-11-13"],
        "max_tokens": 123,
        "temperature": 0,
        "output_format": outputs.ChangelogCopy,
        "messages": [{"role": "user", "content": "Write copy"}],
    }


def test_openai_structured_client_maps_responses_parse_arguments() -> None:
    parsed = outputs.BreakingChangesOutput(bullets=[])
    fake = FakeOpenAIClient(parsed)
    client = providers.OpenAIStructuredLLMClient(fake, model="gpt-test")

    result = client.parse_structured_output(
        prompt="Summarize breaking changes",
        output_model=outputs.BreakingChangesOutput,
        max_output_tokens=456,
        call_name="breaking",
    )

    assert result == parsed
    assert fake.responses.kwargs == {
        "model": "gpt-test",
        "input": [{"role": "user", "content": "Summarize breaking changes"}],
        "text_format": outputs.BreakingChangesOutput,
        "max_output_tokens": 456,
        "temperature": 0,
        "store": False,
    }


def test_openai_structured_client_fails_closed_when_output_parsed_missing() -> None:
    client = providers.OpenAIStructuredLLMClient(FakeOpenAIClient(None), model="gpt-test")

    with pytest.raises(providers.LLMProviderRetryableError, match="did not include output_parsed"):
        client.parse_structured_output(
            prompt="Summarize",
            output_model=outputs.BreakingChangesOutput,
            max_output_tokens=100,
            call_name="breaking",
        )


def test_openai_structured_client_fails_closed_on_incomplete_response() -> None:
    client = providers.OpenAIStructuredLLMClient(
        FakeOpenAIClient(None, status="incomplete", incomplete_details={"reason": "max_output_tokens"}),
        model="gpt-test",
    )

    with pytest.raises(providers.LLMProviderNonRetryableError, match="was incomplete"):
        client.parse_structured_output(
            prompt="Summarize",
            output_model=outputs.BreakingChangesOutput,
            max_output_tokens=100,
            call_name="breaking",
        )


def test_openai_structured_client_fails_closed_on_refusal() -> None:
    refusal_output = [
        SimpleNamespace(
            type="message",
            content=[SimpleNamespace(type="refusal")],
        )
    ]
    client = providers.OpenAIStructuredLLMClient(
        FakeOpenAIClient(None, output=refusal_output),
        model="gpt-test",
    )

    with pytest.raises(providers.LLMProviderNonRetryableError, match="was refused"):
        client.parse_structured_output(
            prompt="Summarize",
            output_model=outputs.BreakingChangesOutput,
            max_output_tokens=100,
            call_name="breaking",
        )


def test_build_structured_llm_client_from_env_selects_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: dict[str, Any] = {}

    class FakeOpenAIConstructor:
        def __init__(self, **kwargs: Any) -> None:
            created.update(kwargs)
            self.responses = FakeOpenAIResponses(outputs.BreakingChangesOutput(bullets=[]))

    monkeypatch.setenv(providers.LLM_PROVIDER_ENV, "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setenv(providers.LLM_MODEL_ENV, "gpt-custom")
    monkeypatch.setattr(providers, "OpenAI", FakeOpenAIConstructor)

    client = providers.build_structured_llm_client_from_env()

    assert isinstance(client, providers.OpenAIStructuredLLMClient)
    assert client.model == "gpt-custom"
    assert created == {"api_key": "openai-token", "max_retries": 0}


def test_build_structured_llm_client_from_env_keeps_anthropic_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: dict[str, Any] = {}

    class FakeAnthropicConstructor(FakeAnthropicClient):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__()
            created.update(kwargs)

    monkeypatch.delenv(providers.LLM_PROVIDER_ENV, raising=False)
    monkeypatch.delenv(providers.LLM_MODEL_ENV, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-token")
    monkeypatch.setattr(providers, "Anthropic", FakeAnthropicConstructor)

    client = providers.build_structured_llm_client_from_env()

    assert isinstance(client, providers.AnthropicStructuredLLMClient)
    assert client.model == providers.DEFAULT_ANTHROPIC_MODEL
    assert created == {"api_key": "anthropic-token"}


def test_blank_env_values_behave_like_missing_for_anthropic_default(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, Any] = {}

    class FakeAnthropicConstructor(FakeAnthropicClient):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__()
            created.update(kwargs)

    monkeypatch.setenv(providers.LLM_PROVIDER_ENV, "   ")
    monkeypatch.setenv(providers.LLM_MODEL_ENV, "  \n ")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-token")
    monkeypatch.setattr(providers, "Anthropic", FakeAnthropicConstructor)

    client = providers.build_structured_llm_client_from_env()

    assert isinstance(client, providers.AnthropicStructuredLLMClient)
    assert client.model == providers.DEFAULT_ANTHROPIC_MODEL
    assert created == {"api_key": "anthropic-token"}


def test_direct_structured_client_factory_rejects_unknown_provider() -> None:
    with pytest.raises(RuntimeError, match="Unsupported LLM provider"):
        providers.build_structured_llm_client(
            provider="not-real",  # type: ignore[arg-type]
            api_key="token",
        )


def test_blank_anthropic_api_key_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(providers.LLM_PROVIDER_ENV, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        providers.build_structured_llm_client_from_env()


def test_blank_openai_api_key_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(providers.LLM_PROVIDER_ENV, "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "   ")

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        providers.build_structured_llm_client_from_env()
