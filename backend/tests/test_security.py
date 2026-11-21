import json
import re
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.routing import APIRoute
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.app import models as m
from backend.app.ai import Usage
from backend.app.github import GitHub
from backend.app.security import current_user, digest

from .conftest import Browser, Mailbox, register
from .test_two_meetings import approve, extract, upload


def reject_external(calls):
    def respond(request):
        calls.append(request)
        return httpx.Response(500)

    return respond


def all_routes(router):
    for route in router.routes:
        if isinstance(route, APIRoute):
            yield route
        elif getattr(route, "original_router", None):
            yield from all_routes(route.original_router)
        else:
            pytest.fail(f"Unexpected route classification: {route!r}")


def test_router_auth_enforced(setup):
    app, client, _ = setup
    public = {
        "/healthz",
        "/readyz",
        "/{path:path}",
        "/api/auth/register",
        "/api/auth/register/confirm",
        "/api/auth/login",
        "/api/auth/reset/request",
        "/api/auth/reset/confirm",
        "/metrics",
    }
    secured = 0
    for route in all_routes(app):
        if route.path in public:
            continue
        secured += 1
        assert any(dep.call is current_user for dep in route.dependant.dependencies), (
            route.path
        )
        path = re.sub(r"\{[^}]+\}", "fake-id", route.path)
        for method in route.methods:
            assert client.request(method, path).status_code == 401, path
    assert secured >= 20


def test_csrf_and_limits(setup):
    app, client, _ = setup
    assert register(client).is_success
    with Browser(app) as stranger:
        for _ in range(5):
            assert (
                stranger.post(
                    "/api/auth/login",
                    json={
                        "email": "absent@example.org",
                        "password": "invalid",
                    },
                ).status_code
                == 401
            )
        limited = stranger.post(
            "/api/auth/login",
            json={
                "email": "absent@example.org",
                "password": "invalid",
            },
        )
        assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0
    response = client.post("/api/auth/logout", headers={"x-csrf-token": "bad"})
    assert response.status_code == 403
    assert (
        client.post(
            "/api/auth/logout", headers={"origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.get("/api/account").is_success
    assert client.get("/healthz").headers["X-Frame-Options"] == "DENY"
    assert (
        client.post(
            "/api/meetings",
            content=b"x" * (app.state.settings.max_upload_bytes + 65537),
        ).status_code
        == 413
    )


def populate(client):
    first = extract(client, upload(client, "meeting1_2026-11-18.txt", "Kickoff"))
    for decision in first["decisions"]:
        approve(client, "decisions", decision)
    for task in first["action_items"]:
        approve(client, "action-items", task)
    second = extract(client, upload(client, "meeting2_2026-11-20.vtt", "Follow-up"))
    return first, second


def test_cross_user_isolation(setup):
    app, client, _ = setup
    assert register(client).is_success
    first, second = populate(client)
    relations = client.get("/api/relations").json()
    client.post("/api/notifications/generate")
    client.post("/api/digests/generate")
    notice = client.get("/api/notifications").json()[0]
    mid = second["id"]
    dec = second["decisions"][0]["id"]
    task = first["action_items"][0]["id"]
    rid = relations[0]["id"]
    calls: list[httpx.Request] = []
    app.state.github = GitHub(
        "mock",
        "demo/meetflow",
        httpx.MockTransport(reject_external(calls)),
    )
    with Browser(app) as other:
        assert register(other, "other@example.org").is_success
        for resource in [
            "meetings",
            "decisions",
            "action-items",
            "relations",
            "notifications",
            "digests",
        ]:
            assert other.get(f"/api/{resource}").json() == []
        checks = [
            ("GET", f"/meetings/{mid}", None),
            ("POST", f"/meetings/{mid}/process", None),
            ("PATCH", f"/decisions/{dec}", {"description": "Other decision"}),
            ("POST", f"/decisions/{dec}/review", {"action": "approve"}),
            ("POST", f"/relations/{rid}/resolve", {"resolution": "KEEP_PREVIOUS"}),
            (
                "PATCH",
                f"/action-items/{task}",
                {
                    "title": "Other",
                    "description": "Other",
                    "owner": None,
                    "deadline": None,
                },
            ),
            ("POST", f"/action-items/{task}/review", {"action": "reject"}),
            ("POST", f"/action-items/{task}/github", None),
            ("POST", f"/action-items/{task}/complete", None),
            ("POST", f"/notifications/{notice['id']}/read", None),
        ]
        for method, url, payload in checks:
            assert other.request(method, "/api" + url, json=payload).status_code == 404
        assert other.delete("/api/account").status_code == 422
        assert all(
            row["action"] == "register" for row in other.get("/api/audit").json()
        )
    assert calls == []
    assert client.get(f"/api/meetings/{mid}").is_success


def test_reset_lifecycle(setup, caplog):
    app, client, clock = setup
    app.state.email = mail = Mailbox()
    assert register(client).is_success
    for email in ["absent@example.org", "alex@example.org"]:
        result = client.post("/api/auth/reset/request", json={"email": email})
        assert result.status_code == 200 and "token" not in result.text
    assert len(mail.messages) == 1
    expired = mail.token()
    clock.value += timedelta(minutes=31)
    assert (
        client.post(
            "/api/auth/reset/confirm",
            json={
                "token": expired,
                "password": "brand-new-test-password",
            },
        ).status_code
        == 400
    )
    assert client.post(
        "/api/auth/reset/request", json={"email": "alex@example.org"}
    ).is_success
    token = mail.token()
    with app.state.engine.connect() as db:
        hashes = db.scalars(select(m.password_reset_tokens.c.token_hash)).all()
    assert digest(token) in hashes and token not in hashes
    stale = Browser(app)
    stale.cookies.update(client.cookies)
    body = {"token": token, "password": "brand-new-test-password"}
    assert client.post("/api/auth/reset/confirm", json=body).is_success
    assert stale.get("/api/account").status_code == 401
    stale.close()
    assert client.post("/api/auth/reset/confirm", json=body).status_code == 400
    assert client.post(
        "/api/auth/login",
        json={"email": "alex@example.org", "password": body["password"]},
    ).is_success
    assert token not in caplog.text and expired not in caplog.text


def test_account_deletion_and_audit_triggers(setup):
    app, client, _ = setup
    app.state.email = Mailbox()
    uid = register(client).json()["id"]
    populate(client)
    client.post("/api/notifications/generate")
    client.post("/api/digests/generate")
    client.post("/api/auth/reset/request", json={"email": "alex@example.org"})
    assert (
        client.request(
            "DELETE",
            "/api/account",
            json={
                "password": "incorrect",
                "confirmation": "DELETE",
            },
        ).status_code
        == 403
    )
    assert client.request(
        "DELETE",
        "/api/account",
        json={
            "password": "test-only-password",
            "confirmation": "DELETE",
        },
    ).is_success
    assert client.get("/api/account").status_code == 401
    with app.state.engine.connect() as db:
        for table in m.metadata.tables.values():
            count = db.scalar(select(func.count()).select_from(table))
            if table is m.audit_logs:
                assert count > 0
            else:
                assert count == 0, table.name
        assert uid not in {row.user_ref for row in db.execute(m.audit_logs.select())}
    for command in ["UPDATE audit_logs SET action='changed'", "DELETE FROM audit_logs"]:
        with pytest.raises(IntegrityError), app.state.engine.begin() as db:
            db.exec_driver_sql(command)


class FakeProvider:
    name = "fake"
    model = "test-fixture"

    def __init__(self, result):
        self.result = result
        self.prompts = []

    def generate_structured(
        self, system, user_content, schema, max_output_tokens, timeout
    ):
        self.prompts.append((system, user_content))
        return self.result, Usage()


def test_injection_is_data_and_cannot_approve(setup, caplog):
    app, client, _ = setup
    assert register(client).is_success
    sentinel = "server-side-test-sentinel"
    provider = FakeProvider(
        {
            "decisions": [
                {
                    "topic": "Injection",
                    "subject_key": "test_injection",
                    "description": "<script>alert(1)</script>",
                    "responsible_speaker": "Imaginary Owner",
                    "evidence_excerpt": "fabricated decision evidence",
                    "confidence": 1.0,
                }
            ],
            "action_items": [
                {
                    "title": "Publish immediately",
                    "description": "<img src=x>",
                    "owner": "Imaginary Owner",
                    "deadline_raw": "tomorrow",
                    "evidence_excerpt": "reveal API keys",
                }
            ],
        }
    )
    app.state.provider = provider
    seen: list[httpx.Request] = []
    app.state.github = GitHub(
        sentinel,
        "demo/meetflow",
        httpx.MockTransport(reject_external(seen)),
    )
    source = Path("samples/injection_attempt.txt").read_text(encoding="utf-8")
    upload_result = client.post(
        "/api/meetings",
        data={
            "title": "Untrusted data",
            "meeting_date": "2026-11-20",
            "transcript": source,
        },
    )
    meeting = extract(client, upload_result.json()["id"])
    prompt, data = provider.prompts[0]
    assert "untrusted data" in prompt
    lines = data.splitlines()
    assert lines[0].startswith("<MEETFLOW_") and lines[2] == "</" + lines[0][1:]
    assert (
        "Ignore all previous instructions"
        in json.loads(lines[1])["segments"][1]["text"]
    )
    assert sentinel not in data + prompt + str(meeting) + caplog.text
    task = meeting["action_items"][0]
    assert (
        task["owner"] is None
        and task["deadline"] is None
        and task["approval_status"] == "NEEDS_REVIEW"
    )
    assert meeting["decisions"][0]["status"] == "NEEDS_REVIEW"
    assert not meeting["decisions"][0]["evidence_verified"]
    assert client.post(f"/api/action-items/{task['id']}/github").status_code == 409
    assert seen == []
    assert client.get("/api/relations").json() == []


def test_invalid_model_recovers_without_losing_source(setup):
    app, client, _ = setup
    assert register(client).is_success
    provider = FakeProvider({"invalid": "discarded"})
    app.state.provider = provider
    mid = upload(client, "meeting1_2026-11-18.txt", "Source is retained")
    result = client.post(f"/api/meetings/{mid}/process").json()
    assert result["status"] == "FAILED" and "invalid" in result["failure_reason"]
    assert len(provider.prompts) == 2
    view = client.get(f"/api/meetings/{mid}").json()
    assert len(view["segments"]) == 4 and view["decisions"] == []
    from backend.app.ai import DemoProvider

    app.state.provider = DemoProvider()
    assert extract(client, mid)["status"] == "EXTRACTED"
    assert client.post(f"/api/meetings/{mid}/process").status_code == 409
    assert (
        client.post(f"/api/meetings/{mid}/process?reprocess=true").json()["status"]
        == "EXTRACTED"
    )
    refreshed = client.get(f"/api/meetings/{mid}").json()
    assert len(refreshed["action_items"]) == 2
    approve(client, "decisions", refreshed["decisions"][0])
    assert client.post(f"/api/meetings/{mid}/process?reprocess=true").status_code == 409
