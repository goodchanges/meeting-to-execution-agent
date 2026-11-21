import json

import httpx
import pytest
from pydantic import SecretStr

from backend.app.ai import (
    Comparison,
    DemoProvider,
    Extraction,
    LiveProvider,
    ProviderError,
    StrictModel,
)
from backend.app.config import Settings

from .conftest import register
from .test_two_meetings import approve, extract, upload


def response_for(value, *, status="completed", message_status="completed"):
    return httpx.Response(
        200,
        json={
            "status": status,
            "output": [
                {
                    "type": "message",
                    "status": message_status,
                    "content": [{"type": "output_text", "text": value}],
                }
            ],
            "usage": {"input_tokens": 42, "output_tokens": 30},
        },
    )


@pytest.mark.parametrize(
    "result",
    [
        response_for("{}"),
        response_for('{"decisions":[],"action_items":[],"unexpected":true}'),
        response_for('{"decisions":[],"action_items":[]}', status="incomplete"),
        response_for('{"decisions":[],"action_items":[]}', message_status="incomplete"),
        response_for("   "),
    ],
)
def test_json_object_validation_rejects_missing_fields_and_incomplete_output(
    result, monkeypatch
):
    def fake_post(url, **request):
        body = request["json"]
        assert body["text"]["format"] == {"type": "json_object"}
        _, schema = body["instructions"].rsplit("\n", 1)
        assert json.loads(schema)["required"] == ["decisions", "action_items"]
        assert url == "https://api.deepseek.com/responses"
        return result

    monkeypatch.setattr("backend.app.ai.httpx.post", fake_post)
    provider = LiveProvider(
        Settings(
            deepseek_api_key=SecretStr("synthetic-credential"),
            deepseek_output_format="json_object",
        )
    )
    with pytest.raises(ProviderError, match="invalid or incomplete") as exc:
        provider.generate_structured(
            "Extract.", "Synthetic meeting.", Extraction, 256, 5
        )
    assert exc.value.invalid


@pytest.mark.parametrize("output_format", ["json_schema", "json_object"])
def test_deepseek_responses_adapter_meeting_pipeline(setup, monkeypatch, output_format):
    app, client, _ = setup
    settings = app.state.settings
    settings.ai_mode = "live"
    settings.deepseek_output_format = output_format
    settings.deepseek_api_key = SecretStr("synthetic-credential")
    app.state.provider = LiveProvider(settings)
    fixture = DemoProvider()
    schemas = []

    def fake_post(url, **request):
        assert url == "https://api.deepseek.com/responses"
        body = request["json"]
        config = body["text"]["format"]
        assert config["type"] == output_format
        if output_format == "json_schema":
            sent_schema = config["schema"]
            assert config["name"] == sent_schema["title"]
        else:
            sent_schema = json.loads(body["instructions"].rsplit("\n", 1)[1])
        schemas_by_name: dict[str, type[StrictModel]] = {
            "Extraction": Extraction,
            "Comparison": Comparison,
        }
        schema = schemas_by_name[sent_schema["title"]]
        assert sent_schema == schema.model_json_schema()
        schemas.append(schema.__name__)
        result, _ = fixture.generate_structured(
            body["instructions"],
            body["input"],
            schema,
            body["max_output_tokens"],
            request["timeout"],
        )
        return response_for(result.model_dump_json())

    monkeypatch.setattr("backend.app.ai.httpx.post", fake_post)
    assert register(client).is_success
    first = extract(client, upload(client, "meeting1_2026-11-18.txt", "First"))
    assert first["processing_mode"] == "live"
    assert {row["owner"]: row["deadline"] for row in first["action_items"]} == {
        "Rahul": "2026-12-02",
        "Sarah": "2026-11-27",
    }
    for decision in first["decisions"]:
        approve(client, "decisions", decision)

    second = extract(client, upload(client, "meeting2_2026-11-20.vtt", "Second"))
    assert second["action_items"][0]["owner"] == "Alex"
    assert second["action_items"][0]["deadline"] == "2026-12-05"
    relations = client.get("/api/relations").json()
    assert {row["relation"] for row in relations} == {"SUPERSEDES", "CONSISTENT"}
    assert schemas == ["Extraction", "Extraction", "Comparison", "Comparison"]
