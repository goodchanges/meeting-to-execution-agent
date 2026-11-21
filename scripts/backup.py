import argparse
import os
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from backend.app.config import Settings


def copy_database(source: Path, destination: Path):
    if not source.is_file():
        raise FileNotFoundError("SQLite source does not exist.")
    if destination.exists() or source.resolve() == destination.resolve():
        raise FileExistsError("Choose an unused destination path.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(f".meetflow-{uuid4().hex}.partial")
    os.close(os.open(part, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    try:
        with closing(
            sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
        ) as origin:
            with closing(sqlite3.connect(part)) as target:
                origin.backup(target, pages=250, sleep=0.05)
                target.execute("PRAGMA journal_mode=DELETE")
                if target.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise RuntimeError("SQLite integrity check failed.")
        os.link(part, destination)
    finally:
        part.unlink(missing_ok=True)


def backup(source: Path, directory: Path, retain: int = 14):
    if retain < 1:
        raise ValueError("BACKUP_RETAIN must be at least 1.")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = directory / f"meetflow-{stamp}.sqlite"
    copy_database(source, target)
    snapshots = (
        path
        for path in directory.iterdir()
        if re.fullmatch(r"meetflow-\d{8}T\d{12}Z\.sqlite", path.name)
    )
    for old in sorted(snapshots, reverse=True)[retain:]:
        old.unlink()
    return target


def main():
    parser = argparse.ArgumentParser(description="Create a consistent SQLite snapshot.")
    parser.add_argument("--source", type=Path, default=Settings().db_path)
    parser.add_argument(
        "--directory", type=Path, default=Path(os.getenv("BACKUP_DIR", "backups"))
    )
    parser.add_argument(
        "--retain", type=int, default=int(os.getenv("BACKUP_RETAIN", "14"))
    )
    args = parser.parse_args()
    print(backup(args.source, args.directory, args.retain))


if __name__ == "__main__":
    main()
