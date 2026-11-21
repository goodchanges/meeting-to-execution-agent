from datetime import timedelta

from sqlalchemy import func, select

from backend.app import models as m

from .conftest import Browser, Mailbox, register


def test_signup_responses_do_not_disclose_account_existence(setup):
    app, client, _ = setup
    assert register(client).status_code == 201
    app.state.email = mail = Mailbox()
    with Browser(app) as visitor:
        known = visitor.post("/api/auth/register", json={"email": " ALEX@EXAMPLE.ORG "})
        new = visitor.post("/api/auth/register", json={"email": "new@example.org"})
        assert known.status_code == new.status_code == 202
        assert known.content == new.content
        for response in (known, new):
            assert "set-cookie" not in response.headers
            assert response.headers["cache-control"] == "no-store"
        assert visitor.get("/api/account").status_code == 401

        for email in ("alex@example.org", "new@example.org"):
            result = visitor.post(
                "/api/auth/login", json={"email": email, "password": "wrong-password"}
            )
            assert result.status_code == 401
            assert result.json()["message"] == "Email or password is incorrect."

        assert [message[0] for message in mail.messages] == ["new@example.org"]
        with app.state.engine.connect() as db:
            assert db.scalar(select(func.count()).select_from(m.users)) == 1

        assert (
            visitor.post(
                "/api/auth/register/confirm",
                json={
                    "token": mail.token(),
                    "password": "example-test-password",
                    "display_name": "New",
                },
            ).status_code
            == 201
        )
        assert visitor.get("/api/account").json()["email"] == "new@example.org"
        with app.state.engine.connect() as db:
            assert db.scalar(select(func.count()).select_from(m.users)) == 2


def test_signup_link_expiry_and_reuse(setup):
    app, client, clock = setup
    app.state.email = mail = Mailbox()
    payload = {"email": "new@example.org"}
    assert client.post("/api/auth/register", json=payload).status_code == 202
    data = {
        "token": mail.token(),
        "password": "example-test-password",
        "display_name": "New",
    }
    clock.value += timedelta(minutes=31)
    expired = client.post("/api/auth/register/confirm", json=data)
    assert expired.status_code == 400

    assert client.post("/api/auth/register", json=payload).status_code == 202
    data["token"] = mail.token()
    assert client.post("/api/auth/register/confirm", json=data).status_code == 201
    reused = client.post("/api/auth/register/confirm", json=data)
    assert reused.status_code == 400
    assert reused.json()["message"] == expired.json()["message"]
    with app.state.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(m.users)) == 1
        assert db.scalar(select(func.count()).select_from(m.registration_tokens)) == 0
