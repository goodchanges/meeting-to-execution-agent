from pathlib import Path

from alembic import command
from alembic.config import Config

from backend.app.db import engine_for
from scripts.backup import backup, copy_database
from scripts.verify_restore import inspect, verify

from .conftest import register
from .test_security import populate


def test_pre_migration_snapshot_is_restorable(tmp_path):
    source = tmp_path / "old.sqlite"
    engine = engine_for(source)
    cfg = Config("alembic.ini")
    with engine.connect() as db:
        cfg.attributes["connection"] = db
        command.upgrade(cfg, "0001")
    snapshot = backup(source, tmp_path / "backups")
    with engine.connect() as db:
        cfg.attributes["connection"] = db
        command.upgrade(cfg, "head")
    engine.dispose()
    assert "ai_monthly_totals" in inspect(source)
    assert verify(snapshot)["meetings"] == 0
    assert "ai_monthly_totals" not in verify(snapshot)


def test_online_backup_and_restore(setup, tmp_path: Path):
    app, client, _ = setup
    assert register(client).is_success
    first, second = populate(client)
    engine = app.state.engine
    with engine.connect() as db:
        assert db.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        snapshot = backup(app.state.settings.db_path, tmp_path / "backups")
        counts = verify(snapshot)
        assert counts["meetings"] == 2
        assert counts["decisions"] == 4
        assert counts["decision_relations"] == 2
        assert counts["action_items"] == 3
        restored = tmp_path / "restored.sqlite"
        copy_database(snapshot, restored)
        assert inspect(restored) == counts
        assert {first["id"], second["id"]} == {
            row["id"] for row in client.get("/api/meetings").json()
        }
