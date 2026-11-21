from pathlib import Path

import httpx

from backend.app.github import GitHub

from .conftest import register


def upload(client, filename, title):
    mime = "text/vtt" if filename.endswith(".vtt") else "text/plain"
    result = client.post(
        "/api/meetings",
        data={"title": title},
        files={
            "file": (filename, (Path("samples") / filename).read_bytes(), mime),
        },
    )
    assert result.status_code == 201, result.text
    return result.json()["id"]


def extract(client, mid):
    result = client.post(f"/api/meetings/{mid}/process")
    assert result.json()["status"] == "EXTRACTED", result.text
    return client.get(f"/api/meetings/{mid}").json()


def approve(client, where, row):
    response = client.post(
        f"/api/{where}/{row['id']}/review", json={"action": "approve"}
    )
    assert response.status_code == 200, response.text


def test_two_meeting_scenario(setup):
    app, client, _ = setup
    # Fixture-backed LLM provider and mocked GitHub HTTP.
    assert register(client).status_code == 201
    assert client.get("/api/account").json()["ai_mode"] == "demo"
    requests = []

    def github(request):
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/repos/demo/meetflow/issues"
        assert b"meetflow:action_item:" in request.content
        assert b"Prepare the launch checklist" in request.content
        return httpx.Response(
            201,
            json={"number": 7, "html_url": "https://github.com/demo/meetflow/issues/7"},
        )

    app.state.github = GitHub(
        "mock-token", "demo/meetflow", httpx.MockTransport(github)
    )
    assert client.patch(
        "/api/settings",
        json={"timezone": "Asia/Kolkata"},
    ).is_success
    m1 = extract(client, upload(client, "meeting1_2026-11-18.txt", "Kickoff"))
    assert len(m1["segments"]) == 4
    assert m1["segments"][0]["speaker_label"] == "Alex"
    assert m1["segments"][0]["start_ts"] == "00:00:05"
    assert {item["deadline"] for item in m1["action_items"]} == {
        "2026-11-27",
        "2026-12-02",
    }
    for decision in m1["decisions"]:
        approve(client, "decisions", decision)
    for task in m1["action_items"]:
        approve(client, "action-items", task)
    m2 = extract(client, upload(client, "meeting2_2026-11-20.vtt", "Launch follow-up"))
    before = client.get("/api/relations").json()
    assert {row["relation"] for row in before} == {"SUPERSEDES", "CONSISTENT"}
    change = next(row for row in before if row["relation"] == "SUPERSEDES")
    assert "Dec 15" in change["prior_evidence"]
    assert "Dec 10" in change["new_evidence"]
    assert change["prior"]["meeting"]["title"] == "Kickoff"
    assert change["new"]["meeting"]["title"] == "Launch follow-up"
    task = m2["action_items"][0]
    endpoint = f"/api/action-items/{task['id']}/github"
    assert task["owner"] == "Alex" and task["deadline"] == "2026-12-05"
    assert client.post(endpoint).status_code == 409
    approve(client, "action-items", task)
    assert client.post(endpoint).status_code == 409
    assert requests == []
    assert client.post(
        f"/api/relations/{change['id']}/resolve",
        json={"resolution": "ACCEPT_NEW_SUPERSEDES"},
    ).is_success
    history = {row["id"]: row for row in client.get("/api/decisions").json()}
    old = history[change["prior_decision_id"]]
    assert old["status"] == "SUPERSEDED"
    assert old["superseded_by_decision_id"] == change["new_decision_id"]
    assert history[change["new_decision_id"]]["status"] == "APPROVED"
    assert client.post(endpoint + "?expected_repo=other/repo").status_code == 409
    assert requests == []
    result = client.post(endpoint + "?expected_repo=demo/meetflow").json()
    assert result["github_state"] == "CREATED"
    assert result["github_issue_url"] == "https://github.com/demo/meetflow/issues/7"
    assert (
        client.post(endpoint).json()["github_issue_url"] == result["github_issue_url"]
    )
    assert len(requests) == 1
    assert client.post("/api/notifications/generate").json()["created"] == 3
    assert client.post("/api/notifications/generate").json()["created"] == 0
    assert {row["kind"] for row in client.get("/api/notifications").json()} == {
        "OVERDUE",
        "UPCOMING_DEADLINE",
    }
    for _ in range(2):
        assert client.post("/api/digests/generate").json()["generated"] == 3
    digests = client.get("/api/digests").json()
    assert {row["person_name"] for row in digests} == {"Alex", "Rahul", "Sarah"}
    assert len(digests) == 3 and all(
        row["week_start"] == "2026-11-30" for row in digests
    )
    assert all(row["processing_mode"] == "demo" for row in digests)
