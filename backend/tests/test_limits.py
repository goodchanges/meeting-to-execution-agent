import json

import httpx
from pydantic import SecretStr

from backend.app.ai import DemoProvider, LiveProvider

from .conftest import register
from .test_two_meetings import upload


class CountingProvider(DemoProvider):
    name = "fake"
    model = "test-model"

    def __init__(self):
        self.calls = 0

    def generate_structured(self, *args, **kwargs):
        self.calls += 1
        return super().generate_structured(*args, **kwargs)


def test_paid_attempt_cap_survives_account_deletion(setup):
    app, client, _ = setup
    app.state.settings.ai_global_monthly_call_cap = 1
    app.state.provider = p = CountingProvider()
    assert register(client).is_success
    first = upload(client, "meeting1_2026-11-18.txt", "First")
    assert client.post(f"/api/meetings/{first}/process").json()["status"] == "EXTRACTED"
    assert client.request(
        "DELETE",
        "/api/account",
        json={
            "password": "test-only-password",
            "confirmation": "DELETE",
        },
    ).is_success
    assert register(client).is_success
    other = upload(client, "meeting1_2026-11-18.txt", "Another")
    failed = client.post(f"/api/meetings/{other}/process").json()
    assert failed["status"] == "FAILED" and "monthly" in failed["failure_reason"]
    assert p.calls == 1


def test_metrics_bearer_and_ai_latency_partition(setup):
    app, client, _ = setup
    assert client.get("/metrics").status_code == 404
    app.state.settings.metrics_token = SecretStr("test-metrics-token")
    assert client.get("/metrics").status_code == 401
    assert register(client).is_success
    mid = upload(client, "meeting1_2026-11-18.txt", "Fixture")
    assert client.post(f"/api/meetings/{mid}/process").is_success
    result = client.get(
        "/metrics", headers={"Authorization": "Bearer test-metrics-token"}
    )
    assert result.is_success
    assert result.json()["ai"]["calls"] == 1
    route = result.json()["api"]["POST /api/meetings/{meeting_id}/process"]
    assert route["requests"] == 1 and route["p95_ms"] is None


def test_deepseek_adapter_repairs_bad_json_and_passes_no_tools(setup, monkeypatch):
    app, client, _ = setup
    settings = app.state.settings
    settings.deepseek_api_key = SecretStr("test-placeholder-provider-key")
    settings.ai_mode = "live"
    settings.llm_model = "deepseek-flash"
    settings.deepseek_output_format = "json_schema"
    app.state.provider = LiveProvider(settings)
    calls = []

    def mock_post(url, **request):
        calls.append(request)
        assert url == "https://api.deepseek.com/responses"
        body = request["json"]
        assert body["model"] == "deepseek-flash"
        assert body["reasoning"] == {"effort": "none"}
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["schema"]["additionalProperties"] is False
        assert "tools" not in body
        assert "test-placeholder-provider-key" not in str(body)
        output = (
            "not-json"
            if len(calls) == 1
            else json.dumps({"decisions": [], "action_items": []})
        )
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": output}],
                    }
                ],
                "usage": {"input_tokens": 51, "output_tokens": 18},
            },
        )

    monkeypatch.setattr("backend.app.ai.httpx.post", mock_post)
    assert register(client).is_success
    mid = upload(client, "meeting1_2026-11-18.txt", "Live adapter mocked")
    assert client.post(f"/api/meetings/{mid}/process").json()["status"] == "EXTRACTED"
    assert len(calls) == 2
    assert "previous response failed validation" in calls[1]["json"]["instructions"]
