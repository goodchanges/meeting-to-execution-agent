import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from backend.app.config import Settings
from backend.app.db import engine_for
from scripts.backup import backup


def main():
    settings = Settings()
    config = Config("alembic.ini")
    head = ScriptDirectory.from_config(config).get_current_head()
    existing = settings.db_path.is_file() and settings.db_path.stat().st_size > 0
    engine = engine_for(settings.db_path)
    with engine.connect() as db:
        revision = MigrationContext.configure(db).get_current_revision()
    if existing and revision != head:
        backup(
            settings.db_path,
            Path(os.getenv("BACKUP_DIR", "backups")),
            int(os.getenv("BACKUP_RETAIN", "14")),
        )
    command.upgrade(config, "head")
    engine.dispose()
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            os.getenv("PORT", "8000"),
            "--workers",
            "1",
            "--no-access-log",
            "--no-proxy-headers",
        ],
    )


if __name__ == "__main__":
    main()
