import json
from datetime import date

import httpx
import pytest

from backend.app.github import GitHub
from backend.app.workflow import deadline_resolved

from .conftest import register
from .test_security import FakeProvider
from .test_two_meetings import approve, extract


@pytest.mark.parametrize(
    ("deadline", "raw", "confirmed", "resolved"),
    [
        (None, None, False, False),
        (None, None, True, True),
        (None, "sometime soon", False, False),
        (None, "sometime soon", True, False),
        (date(2026, 12, 5), "Dec 5", False, True),
    ],
)
def test_deadline_resolution(deadline, raw, confirmed, resolved):
    assert (
        deadline_resolved(
            {
                "deadline": deadline,
                "deadline_raw": raw,
                "no_deadline_confirmed": confirmed,
            }
        )
        is resolved
    )


@pytest.mark.parametrize(
    ("raw", "source", "date_text"),
    [
        (None, "I will write the release notes.", None),
        (
            "sometime soon",
            "I will write the release notes sometime soon.",
            "2026-12-05",
        ),
        ("Dec 5", "I will write the release notes by Dec 5.", "2026-12-05"),
    ],
)
def test_task_deadline_review_and_issue(setup, raw, source, date_text):
    app, client, _ = setup
    assert register(client).is_success
    app.state.provider = FakeProvider(
        {
            "decisions": [],
            "action_items": [
                {
                    "title": "Write the release notes",
                    "description": source,
                    "owner": "Alex",
                    "deadline_raw": raw,
                    "evidence_excerpt": source,
                }
            ],
        }
    )
    response = client.post(
        "/api/meetings",
        data={
            "title": "Release",
            "meeting_date": "2026-11-28",
            "transcript": f"Alex: {source}",
        },
    )
    response.raise_for_status()
    item = extract(client, response.json()["id"])["action_items"][0]
    assert item["owner"] == "Alex"
    assert item["no_deadline_confirmed"] is False

    path = f"/api/action-items/{item['id']}"
    payload = {
        "title": item["title"],
        "description": item["description"],
        "owner": "Alex",
        "deadline": None,
    }
    if raw != "Dec 5":
        assert item["deadline"] is None and item["approval_status"] == "NEEDS_REVIEW"
        assert (
            client.post(path + "/review", json={"action": "approve"}).status_code == 409
        )
        assert client.patch(path, json=payload).is_success
        assert (
            client.post(path + "/review", json={"action": "approve"}).status_code == 409
        )
        if raw:
            assert (
                client.patch(
                    path, json={**payload, "no_deadline_confirmed": True}
                ).status_code
                == 422
            )
            assert client.patch(
                path, json={**payload, "deadline": date_text}
            ).is_success
        else:
            assert client.patch(
                path, json={**payload, "no_deadline_confirmed": True}
            ).is_success
    else:
        assert item["deadline"] == date_text and item["approval_status"] == "PENDING"

    bodies = []

    def mock_issue(request):
        assert request.url.path == "/repos/demo/meetflow/issues"
        bodies.append(json.loads(request.content)["body"])
        return httpx.Response(
            201,
            json={
                "number": 7,
                "html_url": "https://github.com/demo/meetflow/issues/7",
            },
        )

    app.state.github = GitHub(
        "mock-token", "demo/meetflow", httpx.MockTransport(mock_issue)
    )
    assert client.post(path + "/github").status_code == 409
    approve(client, "action-items", item)
    assert client.post(path + "/github").json()["github_state"] == "CREATED"
    assert (
        len(bodies) == 1 and f"Deadline: {date_text or 'Not specified'}\n" in bodies[0]
    )
    assert client.post("/api/notifications/generate").json()["created"] == int(
        date_text is not None
    )
    assert client.post("/api/digests/generate").is_success
    digest_task = client.get("/api/digests").json()[0]["payload"]["tasks"][0]
    assert digest_task["deadline"] == date_text
    assert digest_task["status"] == ("Upcoming" if date_text else "Open")
