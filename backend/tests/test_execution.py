from datetime import timedelta

import httpx
import pytest

from backend.app import models as m
from backend.app.ai import DemoProvider, Extraction, Usage
from backend.app.github import GitHub

from .conftest import register
from .test_two_meetings import approve, extract, upload


@pytest.mark.parametrize(
    ("failure", "word"),
    [
        (401, "token"),
        (403, "access"),
        (404, "unavailable"),
        (422, "rejected"),
        (429, "rate limited"),
        ("timeout", "respond"),
    ],
)
def test_github_failure_and_duplicate_reconciliation(setup, failure, word):
    app, client, clock = setup
    assert register(client).is_success
    meeting = extract(client, upload(client, "meeting1_2026-11-18.txt", "Kickoff"))
    task = meeting["action_items"][0]
    approve(client, "action-items", task)
    client.patch(
        "/api/settings",
        json={"github_repo": "demo/meetflow", "timezone": "Asia/Kolkata"},
    )
    calls = []
    recovered = {
        "number": 5,
        "html_url": "https://github.com/demo/meetflow/issues/5",
        "body": f"<!-- meetflow:action_item:{task['id']} -->",
    }

    def responder(request):
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json=[recovered])
        if failure == "timeout":
            raise httpx.ReadTimeout("test-only timeout")
        return httpx.Response(failure)

    app.state.github = GitHub("mock-token", httpx.MockTransport(responder))
    endpoint = f"/api/action-items/{task['id']}/github"
    result = client.post(endpoint).json()
    assert result["github_state"] == "FAILED" and word in result["github_error"]
    with app.state.engine.begin() as db:
        db.execute(
            m.action_items.update()
            .where(m.action_items.c.id == task["id"])
            .values(github_state="CREATING", github_claimed_at=clock.value)
        )
    assert client.post(endpoint).status_code == 409 and calls == ["POST"]
    clock.value += timedelta(minutes=6)
    retried = client.post(endpoint).json()
    assert retried["github_state"] == "CREATED"
    assert retried["github_issue_url"] == recovered["html_url"]
    assert calls == ["POST", "GET"]


class ComparisonProvider(DemoProvider):
    name = "fake"
    model = "comparison-fixture"

    def __init__(self, subject, relation):
        self.subject = subject
        self.expected = relation

    def generate_structured(
        self, system, user_content, schema, max_output_tokens, timeout
    ):
        if schema is Extraction:
            text = (
                "Launch is Dec 9, 2026."
                if self.subject == "product_launch_date"
                else "We will keep the same coffee supplier."
            )
            return schema.model_validate(
                {
                    "decisions": [
                        {
                            "description": text,
                            "topic": "Launch date",
                            "subject_key": self.subject,
                            "responsible_speaker": "Sarah",
                            "evidence_excerpt": text,
                            "confidence": 1,
                        }
                    ],
                    "action_items": [],
                }
            ), Usage()
        return super().generate_structured(
            system, user_content, schema, max_output_tokens, timeout
        )

    def relation(self, new, prior):
        return self.expected


@pytest.mark.parametrize(
    ("subject", "relation", "status"),
    [
        ("product_launch_date", "CONFLICT", "NEEDS_REVIEW"),
        ("product_launch_date", "UNCERTAIN", "NEEDS_REVIEW"),
        ("office_supplier", "UNRELATED", "PROPOSED"),
    ],
)
def test_conflict_fixture_paths(setup, subject, relation, status):
    app, client, _ = setup
    assert register(client).is_success
    first = extract(client, upload(client, "meeting1_2026-11-18.txt", "Kickoff"))
    approve(client, "decisions", first["decisions"][0])
    app.state.provider = ComparisonProvider(subject, relation)
    second = client.post(
        "/api/meetings",
        data={
            "title": "Review",
            "meeting_date": "2026-11-21",
            "transcript": "Sarah: Launch is Dec 9, 2026."
            if subject == "product_launch_date"
            else "Sarah: We will keep the same coffee supplier.",
        },
    )
    item = extract(client, second.json()["id"])["decisions"][0]
    comparisons = client.get("/api/relations").json()
    assert item["status"] == status
    if relation == "UNRELATED":
        assert comparisons == []
    else:
        assert [row["relation"] for row in comparisons] == [relation]
        assert (
            client.post(
                f"/api/decisions/{item['id']}/review", json={"action": "approve"}
            ).status_code
            == 409
        )
        assert client.post(
            f"/api/relations/{comparisons[0]['id']}/resolve",
            json={
                "resolution": "KEEP_PREVIOUS",
            },
        ).is_success
        assert {row["status"] for row in client.get("/api/decisions").json()} >= {
            "APPROVED",
            "REJECTED",
        }
