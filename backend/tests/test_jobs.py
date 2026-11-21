from datetime import datetime

from backend.app.jobs import start_jobs

from .conftest import register
from .test_two_meetings import approve, extract, upload


def test_scheduled_digest_uses_account_timezone_and_is_idempotent(setup):
    app, client, clock = setup
    assert register(client).is_success
    meeting = extract(client, upload(client, "meeting1_2026-11-18.txt", "Kickoff"))
    approve(client, "action-items", meeting["action_items"][0])
    scheduler = start_jobs(app)
    try:
        tick = scheduler.get_jobs()[0].func
        clock.value = datetime(2026, 11, 30, 3, 29)
        tick()
        assert client.get("/api/digests").json() == []
        clock.value = datetime(2026, 11, 30, 3, 30)
        tick()
        tick()
        assert len(client.get("/api/digests").json()) == 3
        assert len(client.get("/api/notifications").json()) == 1
    finally:
        scheduler.shutdown()
