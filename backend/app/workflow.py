from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    StringConstraints,
    field_validator,
)
from sqlalchemy import select

from . import models as m
from .ai import clean
from .auth import User
from .db import get_owned_or_404, owned, rows
from .github import GitHubError
from .security import audit, current_user, limit, now

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
Short = Annotated[str, StringConstraints(min_length=1, max_length=180)]
Long = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
Lease = timedelta(minutes=5)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def clean_text(cls, value):
        return clean(value) if isinstance(value, str) else value


class Review(Input):
    action: Literal["approve", "reject"]


class DecisionEdit(Input):
    description: Long
    responsible_speaker: Short | None = None


class TaskEdit(Input):
    title: Short
    description: Long
    owner: Short | None
    deadline: date | None
    no_deadline_confirmed: StrictBool = False


class Resolution(Input):
    resolution: Literal[
        "KEEP_PREVIOUS", "ACCEPT_NEW_SUPERSEDES", "KEEP_BOTH", "DISMISSED_CONSISTENT"
    ]
    note: Long | None = None


def update(db, table, uid, record_id, **values):
    db.execute(
        table.update()
        .where(table.c.user_id == uid, table.c.id == record_id)
        .values(**values)
    )


def blockers(db, uid, *, decision_id=None, meeting_id=None):
    stmt = owned(m.decision_relations, uid).where(
        m.decision_relations.c.resolution == "PENDING",
        m.decision_relations.c.relation != "CONSISTENT",
    )
    if decision_id:
        stmt = stmt.where(m.decision_relations.c.new_decision_id == decision_id)
    if meeting_id:
        stmt = stmt.where(
            m.decision_relations.c.new_decision_id.in_(
                select(m.decisions.c.id).where(
                    m.decisions.c.meeting_id == meeting_id,
                    m.decisions.c.user_id == uid,
                )
            )
        )
    return rows(db, stmt)


@router.get("/decisions")
def decisions(request: Request, user: User):
    with request.app.state.engine.connect() as db:
        return rows(
            db, owned(m.decisions, user["id"]).order_by(m.decisions.c.created_at.desc())
        )


@router.get("/action-items")
def action_items(request: Request, user: User):
    with request.app.state.engine.connect() as db:
        return rows(
            db, owned(m.action_items, user["id"]).order_by(m.action_items.c.deadline)
        )


@router.get("/relations")
def relations(request: Request, user: User):
    uid = user["id"]
    with request.app.state.engine.connect() as db:
        records = rows(db, owned(m.decision_relations, uid))
        for row in records:
            for side in ("new", "prior"):
                decision = get_owned_or_404(
                    db, m.decisions, uid, row[f"{side}_decision_id"]
                )
                meeting = get_owned_or_404(db, m.meetings, uid, decision["meeting_id"])
                row[side] = {
                    "decision": decision,
                    "meeting": {
                        key: meeting[key] for key in ("id", "title", "meeting_date")
                    },
                }
    return records


@router.patch("/decisions/{record_id}")
def edit_decision(record_id: str, data: DecisionEdit, request: Request, user: User):
    uid = user["id"]
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        record = get_owned_or_404(db, m.decisions, uid, record_id)
        if record["status"] not in {"PROPOSED", "NEEDS_REVIEW"}:
            raise HTTPException(409, "Only decisions awaiting review can be edited.")
        update(
            db,
            m.decisions,
            uid,
            record_id,
            **data.model_dump(),
            updated_at=now(request),
        )
        audit(db, request, uid, "edit", "decision", record_id)
    return {"ok": True}


@router.post("/decisions/{record_id}/review")
def review_decision(record_id: str, data: Review, request: Request, user: User):
    uid = user["id"]
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        record = get_owned_or_404(db, m.decisions, uid, record_id)
        if record["status"] not in {"PROPOSED", "NEEDS_REVIEW"}:
            raise HTTPException(409, "Decision is no longer awaiting review.")
        if blockers(db, uid, decision_id=record_id):
            raise HTTPException(409, "Resolve the decision comparison first.")
        status = "APPROVED" if data.action == "approve" else "REJECTED"
        update(db, m.decisions, uid, record_id, status=status, updated_at=now(request))
        audit(db, request, uid, data.action, "decision", record_id)
    return {"status": status}


@router.post("/relations/{record_id}/resolve")
def resolve_relation(record_id: str, data: Resolution, request: Request, user: User):
    uid = user["id"]
    current = now(request)
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        record = get_owned_or_404(db, m.decision_relations, uid, record_id)
        new = get_owned_or_404(db, m.decisions, uid, record["new_decision_id"])
        prior = get_owned_or_404(db, m.decisions, uid, record["prior_decision_id"])
        if record["resolution"] != "PENDING":
            raise HTTPException(409, "This comparison has already been resolved.")
        choice = data.resolution
        if choice == "DISMISSED_CONSISTENT":
            if record["relation"] != "CONSISTENT":
                raise HTTPException(
                    409, "Only consistent comparisons can be acknowledged."
                )
        elif record["relation"] == "CONSISTENT" or new["status"] not in {
            "PROPOSED",
            "NEEDS_REVIEW",
        }:
            raise HTTPException(409, "This comparison cannot change the decision.")
        elif choice == "KEEP_PREVIOUS":
            update(
                db, m.decisions, uid, new["id"], status="REJECTED", updated_at=current
            )
            db.execute(
                m.decision_relations.update()
                .where(
                    m.decision_relations.c.user_id == uid,
                    m.decision_relations.c.new_decision_id == new["id"],
                    m.decision_relations.c.resolution == "PENDING",
                    m.decision_relations.c.relation != "CONSISTENT",
                )
                .values(resolution=choice, resolved_at=current)
            )
        elif choice == "ACCEPT_NEW_SUPERSEDES":
            if prior["status"] != "APPROVED":
                raise HTTPException(
                    409,
                    "The previous decision is no longer active. Review remaining options.",
                )
            # Apply replacements together when every blocking comparison has a human resolution.
        update(
            db,
            m.decision_relations,
            uid,
            record_id,
            resolution=choice,
            resolved_at=current,
            resolution_note=data.note,
        )
        if choice in {"KEEP_BOTH", "ACCEPT_NEW_SUPERSEDES"} and not blockers(
            db, uid, decision_id=new["id"]
        ):
            replacements = rows(
                db,
                owned(m.decision_relations, uid).where(
                    m.decision_relations.c.new_decision_id == new["id"],
                    m.decision_relations.c.resolution == "ACCEPT_NEW_SUPERSEDES",
                ),
            )
            for pair in replacements:
                previous = get_owned_or_404(
                    db, m.decisions, uid, pair["prior_decision_id"]
                )
                if previous["status"] == "APPROVED":
                    update(
                        db,
                        m.decisions,
                        uid,
                        previous["id"],
                        status="SUPERSEDED",
                        superseded_by_decision_id=new["id"],
                        updated_at=current,
                    )
            update(
                db, m.decisions, uid, new["id"], status="APPROVED", updated_at=current
            )
        audit(db, request, uid, "resolve", "decision_relation", record_id)
    return {"resolution": choice}


def deadline_resolved(task: dict) -> bool:
    return task["deadline"] is not None or (
        task["no_deadline_confirmed"] and task["deadline_raw"] is None
    )


@router.patch("/action-items/{record_id}")
def edit_task(record_id: str, data: TaskEdit, request: Request, user: User):
    uid = user["id"]
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        record = get_owned_or_404(db, m.action_items, uid, record_id)
        if record["github_state"] != "NOT_CREATED" or record["completed_at"]:
            raise HTTPException(
                409, "The issue payload is frozen after execution begins."
            )
        if data.no_deadline_confirmed and (
            data.deadline is not None or record["deadline_raw"] is not None
        ):
            raise HTTPException(422, "Resolve the source deadline by entering a date.")
        values = data.model_dump()
        update(
            db,
            m.action_items,
            uid,
            record_id,
            **values,
            owner_resolved=bool(data.owner),
            approval_status="PENDING"
            if data.owner and deadline_resolved({**record, **values})
            else "NEEDS_REVIEW",
            edited_by_user=True,
        )
        audit(db, request, uid, "edit", "action_item", record_id)
    return {"ok": True}


@router.post("/action-items/{record_id}/review")
def review_task(record_id: str, data: Review, request: Request, user: User):
    uid = user["id"]
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        record = get_owned_or_404(db, m.action_items, uid, record_id)
        if record["approval_status"] not in {"PENDING", "NEEDS_REVIEW"}:
            raise HTTPException(409, "Task is no longer awaiting review.")
        if data.action == "approve" and (
            record["approval_status"] == "NEEDS_REVIEW"
            or not record["owner_resolved"]
            or not deadline_resolved(record)
        ):
            raise HTTPException(
                409, "Review and save the owner, deadline and task details first."
            )
        state = "APPROVED" if data.action == "approve" else "REJECTED"
        update(db, m.action_items, uid, record_id, approval_status=state)
        audit(db, request, uid, data.action, "action_item", record_id)
    return {"approval_status": state}


@router.post("/action-items/{record_id}/complete")
def complete_task(record_id: str, request: Request, user: User):
    uid = user["id"]
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        record = get_owned_or_404(db, m.action_items, uid, record_id)
        if (
            record["approval_status"] != "APPROVED"
            or record["github_state"] == "CREATING"
        ):
            raise HTTPException(
                409,
                "Only approved tasks with no issue creation in progress can be completed.",
            )
        if not record["completed_at"]:
            update(db, m.action_items, uid, record_id, completed_at=now(request))
            audit(db, request, uid, "complete", "action_item", record_id)
    return {"ok": True}


@router.post("/action-items/{record_id}/github")
def create_issue(
    record_id: str, request: Request, user: User, expected_repo: str | None = None
):
    uid = user["id"]
    settings = request.app.state.settings
    github = request.app.state.github
    limit(request, "github", settings.rate_github, 3600, uid)
    engine = request.app.state.engine
    current = now(request)
    with engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        item = get_owned_or_404(db, m.action_items, uid, record_id)
        state = item["github_state"]
        if state == "CREATED":
            return {"github_state": state, "github_issue_url": item["github_issue_url"]}
        if (
            item["approval_status"] != "APPROVED"
            or not item["owner_resolved"]
            or not deadline_resolved(item)
            or item["completed_at"]
            or blockers(db, uid, meeting_id=item["meeting_id"])
        ):
            raise HTTPException(
                409,
                "Approve the task and resolve its meeting conflicts before creating an issue.",
            )
        if state == "CREATING" and item["github_claimed_at"] > current - Lease:
            raise HTTPException(409, "Issue creation is already in progress.")
        if state not in {"NOT_CREATED", "FAILED", "CREATING"}:
            raise HTTPException(
                409, "The issue cannot be created in its current state."
            )
        repo = github.repository
        if expected_repo and expected_repo.casefold() != (repo or "").casefold():
            raise HTTPException(
                409,
                "The issue destination changed. Refresh and confirm the repository again.",
            )
        if not github.configured or not repo:
            raise HTTPException(
                409, "Configure a GitHub repository and server token first."
            )
        claimed_repo = item["github_repo"]
        if (
            state != "NOT_CREATED"
            and (claimed_repo or "").casefold() != repo.casefold()
        ):
            raise HTTPException(
                409,
                "The previous attempt used a different or unknown repository. Ask an operator to reconcile it.",
            )
        meeting = get_owned_or_404(db, m.meetings, uid, item["meeting_id"])
        claimed = db.execute(
            m.action_items.update()
            .where(
                m.action_items.c.id == record_id,
                m.action_items.c.user_id == uid,
                m.action_items.c.github_state == state,
            )
            .values(
                github_state="CREATING",
                github_repo=repo,
                github_claimed_at=current,
                github_error=None,
            )
        )
        if claimed.rowcount != 1:
            raise HTTPException(409, "The task has changed. Refresh and try again.")
    issue_id, url, error = None, None, None
    try:
        issue_id, url = github.publish(
            item, meeting, settings.public_url, state != "NOT_CREATED"
        )
    except GitHubError as exc:
        error = str(exc)
    new_state = "FAILED" if error else "CREATED"
    with engine.begin() as db:
        updated = db.execute(
            m.action_items.update()
            .where(
                m.action_items.c.id == record_id,
                m.action_items.c.user_id == uid,
                m.action_items.c.github_state == "CREATING",
                m.action_items.c.github_claimed_at == current,
            )
            .values(
                github_state=new_state,
                github_issue_number=issue_id,
                github_issue_url=url,
                github_error=error,
            )
        )
        if updated.rowcount != 1:
            raise HTTPException(
                409, "The task changed during issue creation. Refresh before retrying."
            )
        audit(
            db,
            request,
            uid,
            "create_issue",
            "action_item",
            record_id,
            "failed" if error else "success",
        )
    return {"github_state": new_state, "github_issue_url": url, "github_error": error}
