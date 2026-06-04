#!/usr/bin/env python3
from __future__ import annotations

from typing import Any, Final, List, Literal, Protocol, TypeVar

from anthropic import (
    Anthropic,
    APIError as AnthropicAPIError,
    AuthenticationError as AnthropicAuthenticationError,
    RateLimitError as AnthropicRateLimitError,
)
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

try:
    from openai import (
        OpenAI,
        APIConnectionError as OpenAIAPIConnectionError,
        APIError as OpenAIAPIError,
        APITimeoutError as OpenAIAPITimeoutError,
        AuthenticationError as OpenAIAuthenticationError,
        BadRequestError as OpenAIBadRequestError,
        PermissionDeniedError as OpenAIPermissionDeniedError,
        RateLimitError as OpenAIRateLimitError,
    )
except ModuleNotFoundError:  # pragma: no cover - direct runs without PEP 723 resolution
    OpenAI = None  # type: ignore[assignment]

    class OpenAIAPIConnectionError(Exception):  # type: ignore[no-redef]
        pass

    class OpenAIAPIError(Exception):  # type: ignore[no-redef]
        pass

    class OpenAIAPITimeoutError(Exception):  # type: ignore[no-redef]
        pass

    class OpenAIAuthenticationError(Exception):  # type: ignore[no-redef]
        pass

    class OpenAIBadRequestError(Exception):  # type: ignore[no-redef]
        pass

    class OpenAIPermissionDeniedError(Exception):  # type: ignore[no-redef]
        pass

    class OpenAIRateLimitError(Exception):  # type: ignore[no-redef]
        pass

try:
    from scripts.changelog_env import env_value, require_env_values
except ModuleNotFoundError:  # pragma: no cover
    from changelog_env import env_value, require_env_values  # type: ignore[no-redef]

TLLMOutput = TypeVar("TLLMOutput", bound=BaseModel)

LLM_PROVIDER_ANTHROPIC: Final = "anthropic"

LLM_PROVIDER_OPENAI: Final = "openai"

LLMProviderName = Literal["anthropic", "openai"]

SUPPORTED_LLM_PROVIDERS: Final = frozenset({LLM_PROVIDER_ANTHROPIC, LLM_PROVIDER_OPENAI})

DEFAULT_LLM_PROVIDER: Final[LLMProviderName] = LLM_PROVIDER_ANTHROPIC

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929"

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"

LLM_PROVIDER_ENV = "CHANGELOG_LLM_PROVIDER"

LLM_MODEL_ENV = "CHANGELOG_LLM_MODEL"

class LLMProviderRetryableError(RuntimeError):
    """Retryable provider/API failure at the structured-output seam."""

class LLMProviderNonRetryableError(RuntimeError):
    """Non-retryable provider/API failure at the structured-output seam."""

class LLMOutputValidationError(LLMProviderRetryableError):
    """Retryable failure when structured model content violates hard contracts."""

    def __init__(self, details: List[str]) -> None:
        self.details = details
        super().__init__("\n".join(f"- {detail}" for detail in details))

class StructuredLLMClient(Protocol):
    def parse_structured_output(
        self,
        *,
        prompt: str,
        output_model: type[TLLMOutput],
        max_output_tokens: int,
        call_name: str,
    ) -> TLLMOutput:
        """Parse a prompt into a Pydantic model using the configured provider."""

class AnthropicStructuredLLMClient:
    def __init__(self, client: Anthropic, model: str = DEFAULT_ANTHROPIC_MODEL) -> None:
        self.client = client
        self.model = model

    def parse_structured_output(
        self,
        *,
        prompt: str,
        output_model: type[TLLMOutput],
        max_output_tokens: int,
        call_name: str,
    ) -> TLLMOutput:
        try:
            response = self.client.beta.messages.parse(
                model=self.model,
                betas=["structured-outputs-2025-11-13"],
                max_tokens=max_output_tokens,
                temperature=0,
                output_format=output_model,
                messages=[{"role": "user", "content": prompt}],
            )
        except AnthropicAuthenticationError:
            raise
        except (AnthropicAPIError, AnthropicRateLimitError) as error:
            raise LLMProviderRetryableError(str(error)) from error
        return response.parsed_output

class OpenAIStructuredLLMClient:
    def __init__(self, client: Any, model: str = DEFAULT_OPENAI_MODEL) -> None:
        self.client = client
        self.model = model

    def parse_structured_output(
        self,
        *,
        prompt: str,
        output_model: type[TLLMOutput],
        max_output_tokens: int,
        call_name: str,
    ) -> TLLMOutput:
        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[{"role": "user", "content": prompt}],
                text_format=output_model,
                max_output_tokens=max_output_tokens,
                temperature=0,
                store=False,
            )
        except (OpenAIAuthenticationError, OpenAIPermissionDeniedError, OpenAIBadRequestError):
            raise
        except (
            OpenAIAPIConnectionError,
            OpenAIAPITimeoutError,
            OpenAIRateLimitError,
            OpenAIAPIError,
        ) as error:
            raise LLMProviderRetryableError(str(error)) from error

        if getattr(response, "status", None) == "incomplete":
            details = getattr(response, "incomplete_details", None)
            raise LLMProviderNonRetryableError(
                f"OpenAI structured output for {call_name} was incomplete; details={details}. "
                "Increase the max_output_tokens cap or inspect the prompt."
            )
        if openai_response_has_refusal(response):
            raise LLMProviderNonRetryableError(f"OpenAI structured output for {call_name} was refused")

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise LLMProviderRetryableError(f"OpenAI structured output for {call_name} did not include output_parsed")
        return parsed

def openai_response_has_refusal(response: Any) -> bool:
    """Detect refusals across the common Responses SDK object shapes."""
    if getattr(response, "refusal", None):
        return True
    for output_item in getattr(response, "output", []) or []:
        if getattr(output_item, "type", None) == "refusal":
            return True
        for content_item in getattr(output_item, "content", []) or []:
            if getattr(content_item, "type", None) == "refusal":
                return True
            if getattr(content_item, "refusal", None):
                return True
    return False

def normalize_llm_provider(provider: str | None) -> LLMProviderName:
    """Normalize a provider name and fail closed for unsupported values."""
    normalized = (provider or DEFAULT_LLM_PROVIDER).strip().lower()
    if normalized == LLM_PROVIDER_ANTHROPIC:
        return LLM_PROVIDER_ANTHROPIC
    if normalized == LLM_PROVIDER_OPENAI:
        return LLM_PROVIDER_OPENAI
    raise RuntimeError(
        f"Unsupported {LLM_PROVIDER_ENV}={normalized!r}. Expected 'anthropic' or 'openai'."
    )


def build_anthropic_structured_llm_client(
    *,
    api_key: str,
    model: str | None = None,
) -> AnthropicStructuredLLMClient:
    return AnthropicStructuredLLMClient(
        Anthropic(api_key=api_key),
        model=model or DEFAULT_ANTHROPIC_MODEL,
    )


def build_openai_structured_llm_client(
    *,
    api_key: str,
    model: str | None = None,
) -> OpenAIStructuredLLMClient:
    if OpenAI is None:
        raise RuntimeError("The openai package is required when CHANGELOG_LLM_PROVIDER=openai")
    return OpenAIStructuredLLMClient(
        OpenAI(api_key=api_key, max_retries=0),
        model=model or DEFAULT_OPENAI_MODEL,
    )


def build_structured_llm_client(
    *,
    provider: LLMProviderName,
    api_key: str,
    model: str | None = None,
) -> StructuredLLMClient:
    if provider == LLM_PROVIDER_ANTHROPIC:
        return build_anthropic_structured_llm_client(api_key=api_key, model=model)
    if provider == LLM_PROVIDER_OPENAI:
        return build_openai_structured_llm_client(api_key=api_key, model=model)
    raise RuntimeError(
        f"Unsupported LLM provider={provider!r}. Expected 'anthropic' or 'openai'."
    )


def build_structured_llm_client_from_env() -> StructuredLLMClient:
    """Build the configured structured-output client, requiring keys only for LLM work."""
    provider = normalize_llm_provider(env_value(LLM_PROVIDER_ENV))
    model_override = env_value(LLM_MODEL_ENV)

    if provider == LLM_PROVIDER_ANTHROPIC:
        api_key = require_env_values(["ANTHROPIC_API_KEY"])["ANTHROPIC_API_KEY"]
    else:
        api_key = require_env_values(["OPENAI_API_KEY"])["OPENAI_API_KEY"]
    return build_structured_llm_client(provider=provider, api_key=api_key, model=model_override)

def llm_retryable() -> Any:
    return retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((LLMProviderRetryableError, ValidationError)),
    )

