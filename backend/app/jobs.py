from datetime import UTC, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import StringConstraints
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from . import models as m
from .auth import User
from .db import get_owned_or_404, owned, rows
from .security import audit, current_user, now
from .workflow import Input, blockers, update

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
Repo = Annotated[
    str,
    StringConstraints(
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,38}/[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,99}$",
    ),
]


class SettingsInput(Input):
    github_repo: Repo | None
    timezone: Annotated[str, StringConstraints(min_length=1, max_length=80)]


def settings_for(db, uid):
    return dict(db.execute(owned(m.app_settings, uid)).mappings().one())


@router.get("/settings")
def get_settings(request: Request, user: User):
    with request.app.state.engine.connect() as db:
        values = settings_for(db, user["id"])
    return {
        "github_repo": values["github_repo"],
        "timezone": values["timezone"],
        "github_ready": request.app.state.github.configured,
    }


@router.patch("/settings")
def edit_settings(data: SettingsInput, request: Request, user: User):
    try:
        ZoneInfo(data.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(
            422, "Use a valid IANA timezone, such as Asia/Kolkata."
        ) from None
    uid = user["id"]
    with request.app.state.engine.begin() as db:
        db.execute(
            m.app_settings.update()
            .where(m.app_settings.c.user_id == uid)
            .values(**data.model_dump())
        )
        audit(db, request, uid, "edit", "settings")
    return {"ok": True}


def local_for(current, settings):
    return current.replace(tzinfo=UTC).astimezone(ZoneInfo(settings["timezone"]))


def open_tasks(db, uid):
    return rows(
        db,
        owned(m.action_items, uid).where(
            m.action_items.c.approval_status == "APPROVED",
            m.action_items.c.completed_at.is_(None),
        ),
    )


def notify(db, uid, prefs, current, window):
    local_day = local_for(current, prefs).date()
    created = 0
    for task in open_tasks(db, uid):
        due = task["deadline"]
        if not due or due > local_day + timedelta(days=window):
            continue
        kind = "OVERDUE" if due < local_day else "UPCOMING_DEADLINE"
        stmt = (
            sqlite_insert(m.notifications)
            .values(
                user_id=uid,
                kind=kind,
                action_item_id=task["id"],
                message=f"{task['owner']} · {task['title']} · Due {due}",
                dedupe_key=f"{kind}:{task['id']}:{due}",
                processing_mode=task["processing_mode"],
            )
            .on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
        )
        created += db.execute(stmt).rowcount
    for relation in blockers(db, uid):
        decision = get_owned_or_404(db, m.decisions, uid, relation["new_decision_id"])
        stmt = (
            sqlite_insert(m.notifications)
            .values(
                user_id=uid,
                kind="CONFLICT_PENDING",
                message=f"Review comparison for {decision['topic']}",
                dedupe_key=f"conflict:{relation['id']}",
                processing_mode=relation["processing_mode"],
            )
            .on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
        )
        created += db.execute(stmt).rowcount
    return created


def digest_people(db, uid, prefs, current, window):
    today = local_for(current, prefs).date()
    monday = today - timedelta(days=today.weekday())
    participants = rows(db, owned(m.meeting_participants, uid))
    tasks = rows(
        db,
        owned(m.action_items, uid).where(
            m.action_items.c.approval_status == "APPROVED"
        ),
    )
    decisions = rows(
        db, owned(m.decisions, uid).where(m.decisions.c.status == "APPROVED")
    )
    pending = blockers(db, uid)
    pending_decisions = {
        row["new_decision_id"]: get_owned_or_404(
            db, m.decisions, uid, row["new_decision_id"]
        )
        for row in pending
    }
    names = sorted(
        {row["name"] for row in participants}
        | {row["owner"] for row in tasks if row["owner"]}
    )
    for name in names:
        assigned = [task for task in tasks if task["owner"] == name]
        meetings = {row["meeting_id"] for row in participants if row["name"] == name}
        meetings.update(task["meeting_id"] for task in assigned)
        relevant = [row for row in decisions if row["meeting_id"] in meetings]
        conflicts = [
            row for row in pending_decisions.values() if row["meeting_id"] in meetings
        ]
        compact = [
            {
                "id": task["id"],
                "title": task["title"],
                "deadline": str(task["deadline"]),
                "status": "Completed"
                if task["completed_at"]
                else "Overdue"
                if task["deadline"] < today
                else "Upcoming"
                if task["deadline"] <= today + timedelta(days=window)
                else "Open",
            }
            for task in assigned
        ]
        payload = {
            "tasks": compact,
            "decisions": [row["description"] for row in relevant],
            "conflicts": [row["topic"] for row in conflicts],
        }
        demo = any(
            row["processing_mode"] == "demo"
            for row in [*assigned, *relevant, *conflicts]
        )
        mode = "demo" if demo else "live"
        db.execute(
            sqlite_insert(m.digests)
            .values(
                user_id=uid,
                person_name=name,
                week_start=monday,
                payload=payload,
                generated_at=current,
                processing_mode=mode,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "person_name", "week_start"],
                set_={
                    "payload": payload,
                    "generated_at": current,
                    "processing_mode": mode,
                },
            )
        )
    return len(names)


@router.get("/notifications")
def notifications(request: Request, user: User):
    with request.app.state.engine.connect() as db:
        return rows(
            db, owned(m.notifications, user["id"]).order_by(m.notifications.c.read_at)
        )


@router.post("/notifications/generate")
def generate_notifications(request: Request, user: User):
    uid = user["id"]
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        count = notify(
            db,
            uid,
            settings_for(db, uid),
            now(request),
            request.app.state.settings.reminder_days,
        )
    return {"created": count}


@router.post("/notifications/{record_id}/read")
def read_notification(record_id: str, request: Request, user: User):
    uid = user["id"]
    with request.app.state.engine.begin() as db:
        get_owned_or_404(db, m.notifications, uid, record_id)
        update(db, m.notifications, uid, record_id, read_at=now(request))
    return {"ok": True}


@router.get("/digests")
def digests(request: Request, user: User):
    with request.app.state.engine.connect() as db:
        return rows(
            db,
            owned(m.digests, user["id"]).order_by(
                m.digests.c.week_start.desc(), m.digests.c.person_name
            ),
        )


@router.post("/digests/generate")
def generate_digests(request: Request, user: User):
    uid = user["id"]
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        count = digest_people(
            db,
            uid,
            settings_for(db, uid),
            now(request),
            request.app.state.settings.reminder_days,
        )
    return {"generated": count}


def start_jobs(app):
    engine, clock = app.state.engine, app.state.clock
    window = app.state.settings.reminder_days
    completed: dict[str, str] = {}

    def tick():
        current = clock()
        with engine.connect() as db:
            all_settings = rows(db, m.app_settings.select())
        active = {prefs["user_id"] for prefs in all_settings}
        for uid in set(completed) - active:
            del completed[uid]
        for prefs in all_settings:
            uid = prefs["user_id"]
            with engine.begin() as db:
                db.exec_driver_sql("BEGIN IMMEDIATE")
                if not db.execute(owned(m.app_settings, uid)).first():
                    continue
                notify(db, uid, prefs, current, window)
                local = local_for(current, prefs)
                stamp = local.date().isoformat()
                if (
                    local.weekday() == 0
                    and local.hour == 9
                    and completed.get(uid) != stamp
                ):
                    digest_people(db, uid, prefs, current, window)
                    completed[uid] = stamp

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(tick, "interval", seconds=60, coalesce=True, max_instances=1)
    scheduler.start()
    return scheduler
