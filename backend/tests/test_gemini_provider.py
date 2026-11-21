import json
from contextlib import contextmanager

import httpx
import pytest
from google import genai
from pydantic import SecretStr

from backend.app.ai import (
    Comparison,
    DemoProvider,
    Extraction,
    ProviderError,
    StrictModel,
)
from backend.app.config import Settings
from backend.app.gemini import GeminiProvider
from backend.app.providers import runtime_provider

from .conftest import register
from .test_two_meetings import approve, extract, upload


def stub_sdk(monkeypatch, handler):
    client = genai.Client

    @contextmanager
    def open_client(**kwargs):
        with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
            kwargs["http_options"].httpx_client = transport
            with client(**kwargs) as sdk:
                yield sdk

    monkeypatch.setattr("backend.app.gemini.genai.Client", open_client)


def gemini_settings():
    return Settings(
        ai_mode="live",
        ai_provider="gemini",
        gemini_model="gemini-3.8-flash",
        gemini_api_key=SecretStr("synthetic-offline-key"),
    )


def interaction_response(result, *, status="completed"):
    return httpx.Response(
        200,
        json={
            "object": "interaction",
            "id": "offline-fixture",
            "status": status,
            "model": "gemini-3.8-flash",
            "steps": [
                {"type": "model_output", "content": [{"type": "text", "text": result}]}
            ],
            "usage": {
                "total_input_tokens": 51,
                "total_output_tokens": 20,
                "total_thought_tokens": 4,
            },
        },
    )


@pytest.mark.parametrize(
    ("result", "status"),
    [
        ("not-json", "completed"),
        ("{}", "completed"),
        ('{"decisions":[],"action_items":[],"unexpected":1}', "completed"),
        ('{"decisions":[],"action_items":[]}', "incomplete"),
        ("", "completed"),
    ],
)
def test_gemini_rejects_malformed_or_incomplete(monkeypatch, result, status):
    stub_sdk(monkeypatch, lambda _: interaction_response(result, status=status))
    with pytest.raises(ProviderError, match="invalid or incomplete") as exc:
        GeminiProvider(gemini_settings()).generate_structured(
            "Extract", "Synthetic", Extraction, 500, 2
        )
    assert exc.value.invalid


def test_sdk_does_not_retry_beyond_meetflow(monkeypatch):
    calls = 0

    def limited(request):
        nonlocal calls
        calls += 1
        assert request.extensions["timeout"]["read"] <= 2
        return httpx.Response(
            429,
            json={
                "error": {
                    "code": 429,
                    "message": "fixture",
                    "status": "RESOURCE_EXHAUSTED",
                }
            },
        )

    stub_sdk(monkeypatch, limited)
    with pytest.raises(ProviderError, match="429") as exc:
        GeminiProvider(gemini_settings()).generate_structured(
            "Extract", "Synthetic", Extraction, 500, 2
        )
    assert exc.value.transient and calls == 1


def test_metadata_authentication_uses_only_get(monkeypatch):
    calls = []

    def metadata(request):
        calls.append((request.method, request.url.path))
        assert request.headers["x-goog-api-key"] == "synthetic-offline-key"
        return httpx.Response(200, json={"name": "models/gemini-3.8-flash"})

    stub_sdk(monkeypatch, metadata)
    GeminiProvider(gemini_settings()).check_model(2)
    assert calls == [("GET", "/v1beta/models/gemini-3.8-flash")]


def test_gemini_native_structured_output_pipeline(setup, monkeypatch, caplog):
    monkeypatch.setenv("GOOGLE_GENAI_DEBUG", "true")
    app, client, _ = setup
    app.state.settings.ai_mode = "live"
    app.state.settings.ai_provider = "gemini"
    app.state.settings.gemini_model = "gemini-3.8-flash"
    app.state.settings.gemini_api_key = SecretStr("synthetic-offline-key")
    app.state.provider = runtime_provider(app.state.settings)
    assert isinstance(app.state.provider, GeminiProvider)

    fixture = DemoProvider()
    seen = []

    def respond(request):
        assert request.url.path == "/v1beta/interactions"
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["x-goog-api-key"] == "synthetic-offline-key"
        body = json.loads(request.content)
        assert body["model"] == "gemini-3.8-flash"
        assert body["store"] is False
        assert "tools" not in body
        assert (
            body["generation_config"]["max_output_tokens"]
            == app.state.settings.max_output_tokens
        )
        config = body["response_format"]
        assert config["mime_type"] == "application/json"
        names: dict[str, type[StrictModel]] = {
            "Extraction": Extraction,
            "Comparison": Comparison,
        }
        schema = names[config["schema"]["title"]]
        assert "$ref" not in json.dumps(config["schema"])
        assert config["schema"]["additionalProperties"] is False
        seen.append(schema.__name__)
        result, _ = fixture.generate_structured(
            body["system_instruction"],
            body["input"],
            schema,
            body["generation_config"]["max_output_tokens"],
            2,
        )
        return interaction_response(result.model_dump_json())

    stub_sdk(monkeypatch, respond)
    assert register(client).is_success
    assert client.get("/api/account").json()["ai_ready"] is True
    first = extract(client, upload(client, "meeting1_2026-11-18.txt", "First"))
    assert {row["owner"]: row["deadline"] for row in first["action_items"]} == {
        "Rahul": "2026-12-02",
        "Sarah": "2026-11-27",
    }
    for decision in first["decisions"]:
        approve(client, "decisions", decision)
    second = extract(client, upload(client, "meeting2_2026-11-20.vtt", "Second"))
    assert second["action_items"][0]["owner"] == "Alex"
    assert second["action_items"][0]["deadline"] == "2026-12-05"
    assert {row["relation"] for row in client.get("/api/relations").json()} == {
        "SUPERSEDES",
        "CONSISTENT",
    }
    assert seen == ["Extraction", "Extraction", "Comparison", "Comparison"]
    assert "synthetic-offline-key" not in caplog.text
