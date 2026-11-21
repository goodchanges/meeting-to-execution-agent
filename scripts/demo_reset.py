from getpass import getpass
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import users
from backend.app.security import CSRF

DEMO_EMAIL = "meetflow-demo@example.org"
DEMO_DB = Path("data/demo.sqlite")


def main():
    settings = Settings()
    if settings.app_env != "development" or settings.ai_mode != "demo":
        raise SystemExit("Demo reset requires APP_ENV=development and AI_MODE=demo.")
    if settings.db_path.resolve() != DEMO_DB.resolve():
        raise SystemExit(
            "Set DB_PATH=data/demo.sqlite to use the dedicated demo database."
        )
    password = getpass("New demo account password (12–128 characters): ")
    if not 12 <= len(password) <= 128:
        raise SystemExit("Use a password between 12 and 128 characters.")
    command.upgrade(Config("alembic.ini"), "head")
    app = create_app(settings.model_copy(update={"scheduler_enabled": False}))
    with app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        uid = db.scalar(select(users.c.id).where(users.c.email == DEMO_EMAIL))
        if uid:
            db.execute(users.delete().where(users.c.id == uid))
    with TestClient(app) as client:
        headers = {"x-meetflow-client": "1"}
        client.post(
            "/api/auth/register",
            headers=headers,
            json={
                "email": DEMO_EMAIL,
                "password": password,
                "display_name": "Alex",
            },
        ).raise_for_status()
        headers["x-csrf-token"] = client.cookies[CSRF]
        sample = Path("samples/meeting1_2026-11-18.txt")
        response = client.post(
            "/api/meetings",
            headers=headers,
            data={"title": "Product launch kickoff"},
            files={"file": (sample.name, sample.read_bytes(), "text/plain")},
        )
        mid = response.raise_for_status().json()["id"]
        result = (
            client.post(f"/api/meetings/{mid}/process", headers=headers)
            .raise_for_status()
            .json()
        )
        if result["status"] != "EXTRACTED":
            raise SystemExit("Demo meeting could not be processed.")
    print(f"DEMO MODE — not live AI. Sign in as {DEMO_EMAIL} and review meeting 1.")


if __name__ == "__main__":
    main()
