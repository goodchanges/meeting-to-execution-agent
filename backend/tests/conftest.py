from datetime import datetime
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.db import engine_for
from backend.app.main import create_app
from backend.app.security import CSRF


class Browser(TestClient):
    def request(self, method, url, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        headers.setdefault("x-meetflow-client", "1")
        if self.cookies.get(CSRF):
            headers.setdefault("x-csrf-token", self.cookies[CSRF])
        return super().request(method, url, headers=headers, **kwargs)


class Mailbox:
    def __init__(self):
        self.messages: list[tuple[str, str, str]] = []

    def send(self, recipient: str, link: str, subject: str):
        self.messages.append((recipient, link, subject))

    def token(self):
        return self.messages[-1][1].split("#token=", 1)[1]


def register(client, email="alex@example.org", password="test-only-password"):
    original = client.app.state.email
    client.app.state.email = mailbox = Mailbox()
    try:
        client.post("/api/auth/register", json={"email": email}).raise_for_status()
        return client.post(
            "/api/auth/register/confirm",
            json={
                "token": mailbox.token(),
                "password": password,
                "display_name": "Alex",
            },
        )
    finally:
        client.app.state.email = original


@pytest.fixture
def setup(tmp_path):
    settings = Settings(
        app_env="test",
        db_path=tmp_path / "test.sqlite",
        scheduler_enabled=False,
        ai_mode="demo",
        rate_general=600,
    )
    config = Config("alembic.ini")
    engine = engine_for(settings.db_path)
    with engine.connect() as db:
        config.attributes["connection"] = db
        command.upgrade(config, "head")
    engine.dispose()
    clock = SimpleNamespace(value=datetime(2026, 12, 3, 8))
    app = create_app(settings, clock=lambda: clock.value)
    with Browser(app) as client:
        yield app, client, clock
