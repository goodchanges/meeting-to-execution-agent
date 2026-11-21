from datetime import timedelta

import httpx
import pytest
from pydantic import ValidationError

from backend.app import models as m
from backend.app.config import Settings
from backend.app.github import GitHub

from .conftest import register
from .test_two_meetings import approve, extract, upload


@pytest.mark.parametrize(
    "name",
    ["https://github.com/owner/repo", "a/b/c", "a/..", "a/b?x=1", "a/b%2fc", "a/b\n"],
)
def test_reject_malformed_github_repo(name, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", name)
    with pytest.raises(ValidationError, match="GITHUB_REPOSITORY"):
        Settings()


def test_github_token_cannot_be_redirected(setup, monkeypatch):
    app, client, clock = setup
    monkeypatch.setenv("GITHUB_REPOSITORY", "fixed-org/workspace")
    repository = Settings().github_repository
    calls = []

    def upstream(request):
        calls.append((request.method, str(request.url)))
        assert request.headers["authorization"] == "Bearer local-test-pat"
        return httpx.Response(
            201,
            json={
                "number": 1,
                "html_url": "https://github.com/fixed-org/workspace/issues/1",
            },
        )

    app.state.github = GitHub(
        "local-test-pat", repository, httpx.MockTransport(upstream)
    )
    assert register(client).is_success
    changed = client.patch(
        "/api/settings", json={"timezone": "Asia/Kolkata", "github_repo": "other/repo"}
    )
    assert changed.status_code == 422
    prefs = client.get("/api/settings")
    assert prefs.json()["github_repo"] == repository
    assert "local-test-pat" not in prefs.text

    meeting = extract(client, upload(client, "meeting1_2026-11-18.txt", "Kickoff"))
    fresh, retry = meeting["action_items"]
    for task in (fresh, retry):
        approve(client, "action-items", task)

    with app.state.engine.begin() as db:
        db.execute(m.app_settings.update().values(github_repo="other/repo"))
        db.execute(
            m.action_items.update()
            .where(m.action_items.c.id.in_([fresh["id"], retry["id"]]))
            .values(github_repo="other/repo")
        )
        db.execute(
            m.action_items.update()
            .where(m.action_items.c.id == retry["id"])
            .values(
                github_state="CREATING",
                github_claimed_at=clock.value - timedelta(minutes=6),
            )
        )

    fresh_path = f"/api/action-items/{fresh['id']}/github"
    retry_path = f"/api/action-items/{retry['id']}/github"
    assert client.post(fresh_path + "?expected_repo=other/repo").status_code == 409
    assert client.post(retry_path).status_code == 409
    assert calls == []
    result = client.post(
        fresh_path + "?repo=other/repo", json={"github_repo": "other/repo"}
    )
    assert result.json()["github_state"] == "CREATED"
    assert (
        client.post(fresh_path).json()["github_issue_url"]
        == result.json()["github_issue_url"]
    )
    assert calls == [
        ("POST", "https://api.github.com/repos/fixed-org/workspace/issues")
    ]
