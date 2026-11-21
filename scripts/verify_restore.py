import argparse
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.models import metadata
from scripts.backup import copy_database


def inspect(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise RuntimeError("SQLite integrity check failed.")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise RuntimeError("Restored database has FK violations.")
        for child, links in {
            "decisions": [
                ("meeting_id", "meetings"),
                ("superseded_by_decision_id", "decisions"),
            ],
            "decision_relations": [
                ("new_decision_id", "decisions"),
                ("prior_decision_id", "decisions"),
            ],
            "action_items": [("meeting_id", "meetings")],
            "notifications": [("action_item_id", "action_items")],
        }.items():
            for key, parent in links:
                if db.execute(
                    f"SELECT 1 FROM {child} c JOIN {parent} p ON p.id = c.{key} "
                    "WHERE c.user_id <> p.user_id LIMIT 1"
                ).fetchone():
                    raise RuntimeError(
                        "Restored database contains cross-owner references."
                    )
        version = db.execute("SELECT version_num FROM alembic_version").fetchone()
        if not version or version[0] not in {"0001", "0002", "0003"}:
            raise RuntimeError(
                "Unsupported MeetFlow schema revision for restore verification."
            )
        tables = set(metadata.tables)
        if version[0] == "0001":
            tables.remove("ai_monthly_totals")
        if version[0] in {"0001", "0002"}:
            tables.remove("registration_tokens")
        elif "no_deadline_confirmed" not in {
            row[1] for row in db.execute("PRAGMA table_info(action_items)")
        }:
            raise RuntimeError("Restored action items lack deadline confirmation.")
        return {
            name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in sorted(tables)
        }


def verify(snapshot):
    with TemporaryDirectory() as directory:
        restored = Path(directory) / "restored.sqlite"
        copy_database(snapshot, restored)
        counts = inspect(restored)
        if counts != inspect(snapshot):
            raise RuntimeError("Snapshot and restore counts differ.")
        return counts


def main():
    parser = argparse.ArgumentParser(
        description="Rehearse a restore and verify counts and foreign keys."
    )
    parser.add_argument("snapshot", type=Path)
    print(verify(parser.parse_args().snapshot))


if __name__ == "__main__":
    main()
