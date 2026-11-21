import logging

import httpx
from google import genai
from google.genai import errors, types

# Interactions and the Models endpoint use separate exception hierarchies in google-genai.
from google.genai._gaos.lib.compat_errors import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
)

from .ai import ProviderError, T, Usage
from .config import Settings


def response_schema(schema: type[T]) -> dict:
    document = schema.model_json_schema()
    definitions = document.get("$defs", {})

    def adapt(node):
        if isinstance(node, list):
            return [adapt(value) for value in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return adapt(definitions[node["$ref"].removeprefix("#/$defs/")])
        # The full original constraints still apply during Pydantic validation.
        adapted = {
            key: adapt(value)
            for key, value in node.items()
            if key not in {"$defs", "minLength", "maxLength", "pattern"}
        }
        variants = adapted.get("anyOf")
        if variants and all(set(value) == {"type"} for value in variants):
            adapted["type"] = [value["type"] for value in adapted.pop("anyOf")]
        return adapted

    return adapt(document)


def request_error(status: int | None) -> ProviderError:
    if status is None:
        return ProviderError("Gemini did not return an HTTP status.", transient=True)
    if status in {401, 403}:
        return ProviderError("Gemini rejected the credentials or their permissions.")
    if status == 404:
        return ProviderError(
            "The configured Gemini model or API endpoint is unavailable."
        )
    return ProviderError(
        f"Gemini rejected the request (HTTP {status}).",
        transient=status in {408, 429} or status >= 500,
    )


class GeminiProvider:
    name = "gemini"

    def __init__(self, settings: Settings):
        self.model = settings.gemini_model
        self.key = settings.gemini_api_key

    def _client(self, timeout: float) -> genai.Client:
        key = self.key.get_secret_value()
        if not key:
            raise ProviderError(
                "Live AI is enabled. Configure GEMINI_API_KEY to process meetings."
            )
        # The SDK debug logger can include request headers. Suppress it for MeetFlow.
        logging.getLogger("google.genai").disabled = True
        return genai.Client(
            api_key=key,
            vertexai=False,
            http_options=types.HttpOptions(
                base_url="https://generativelanguage.googleapis.com",
                api_version="v1beta",
                timeout=int(timeout * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    def check_model(self, timeout: float) -> None:
        try:
            with self._client(timeout) as client:
                metadata = client.models.get(model=self.model)
            if metadata.name != f"models/{self.model.removeprefix('models/')}":
                raise ValueError()
        except errors.APIError as exc:
            raise request_error(exc.code) from None
        except httpx.RequestError:
            raise ProviderError(
                "Gemini model metadata could not be reached.", transient=True
            ) from None
        except (ValueError, TypeError):
            raise ProviderError("Gemini returned invalid model metadata.") from None

    def generate_structured(
        self,
        system: str,
        user_content: str,
        schema: type[T],
        max_output_tokens: int,
        timeout: float,
    ) -> tuple[T, Usage]:
        try:
            with self._client(timeout) as client:
                # The core SDK uses total attempts; Interactions uses this field as extra retries.
                client._api_client._http_options.retry_options = types.HttpRetryOptions(
                    attempts=0
                )
                interaction = client.interactions.create(
                    model=self.model,
                    system_instruction=system,
                    input=user_content,
                    store=False,
                    stream=False,
                    automatic_continuation=False,
                    timeout=timeout,
                    generation_config={
                        "max_output_tokens": max_output_tokens,
                        "thinking_level": "low",
                    },
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": response_schema(schema),
                    },
                )
            if getattr(interaction, "status", None) != "completed":
                raise ValueError()
            output = getattr(interaction, "output_text", None)
            if not isinstance(output, str) or not output.strip():
                raise ValueError()
            result = schema.model_validate_json(output)
            usage = getattr(interaction, "usage", None)
            inputs = getattr(usage, "total_input_tokens", None)
            outputs = getattr(usage, "total_output_tokens", None)
            thoughts = getattr(usage, "total_thought_tokens", None)
            if thoughts is not None:
                outputs = (outputs or 0) + thoughts
            return result, Usage(inputs, outputs)
        except (APIConnectionError, httpx.RequestError):
            raise ProviderError(
                "Gemini could not be reached.", transient=True
            ) from None
        except APIStatusError as exc:
            raise request_error(exc.status_code) from None
        except errors.APIError as exc:
            raise request_error(exc.code) from None
        except (APIResponseValidationError, ValueError, TypeError):
            raise ProviderError(
                "Gemini returned invalid or incomplete structured output.", invalid=True
            ) from None
