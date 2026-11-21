from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import URL, Connection, Table, create_engine, event, select


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def engine_for(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL.create("sqlite", database=str(path.resolve())))

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")

    return engine


def owned(table: Table, user_id: str):
    return select(table).where(table.c.user_id == user_id)


def get_owned_or_404(db: Connection, table: Table, user_id: str, object_id: str):
    row = (
        db.execute(owned(table, user_id).where(table.c.id == object_id))
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(404, "Record not found.")
    return dict(row)


def rows(db: Connection, stmt):
    return [dict(row) for row in db.execute(stmt).mappings()]


def insert(db: Connection, table: Table, **values) -> str:
    return str(db.execute(table.insert().values(**values)).inserted_primary_key[0])
