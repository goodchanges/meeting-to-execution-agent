import secrets
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Annotated, Literal, Protocol
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
)
from pydantic import BaseModel, EmailStr, StringConstraints
from sqlalchemy import select

from . import models as m
from .auth import Password, User
from .config import Settings
from .db import insert, rows
from .security import (
    audit,
    bootstrap_csrf,
    clear_session,
    current_user,
    digest,
    hasher,
    limit,
    now,
    reference,
    verify,
)

bootstrap = APIRouter(prefix="/api/auth/reset", dependencies=[Depends(bootstrap_csrf)])
router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
RESET_MESSAGE = "If the account exists and email delivery is available, a reset link will arrive shortly."


class ResetRequest(BaseModel):
    email: EmailStr


class ResetConfirm(BaseModel):
    token: Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{43}$")]
    password: Password


class Reauth(BaseModel):
    password: Annotated[str, StringConstraints(max_length=128)]


class ChangePassword(Reauth):
    new_password: Password


class DeleteAccount(Reauth):
    confirmation: Literal["DELETE"]


class EmailProvider(Protocol):
    def send(self, recipient: str, link: str) -> None: ...


class DevOutboxEmailProvider:
    def __init__(self, directory: Path):
        self.directory = directory

    def send(self, recipient: str, link: str):
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"{uuid4().hex}.txt").write_text(
            f"To: {recipient}\n\nReset your MeetFlow password: {link}\n",
            encoding="utf-8",
        )


class SmtpEmailProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, recipient: str, link: str):
        settings = self.settings
        message = EmailMessage()
        message["From"] = settings.smtp_sender
        message["To"] = recipient
        message["Subject"] = "Reset your MeetFlow password"
        message.set_content(
            f"Use this link within 30 minutes to reset your password:\n{link}"
        )
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(
                    settings.smtp_username, settings.smtp_password.get_secret_value()
                )
            smtp.send_message(message)


def email_for(settings: Settings) -> EmailProvider | None:
    if settings.app_env == "development":
        return DevOutboxEmailProvider(settings.dev_outbox)
    if settings.smtp_host and settings.smtp_sender:
        return SmtpEmailProvider(settings)
    return None


@bootstrap.post("/request")
def request_reset(data: ResetRequest, request: Request, background: BackgroundTasks):
    settings = request.app.state.settings
    email = data.email.casefold()
    limit(
        request, "reset_request", settings.rate_reset, 3600, reference(request, email)
    )
    provider = request.app.state.email
    if not provider:
        raise HTTPException(503, "Password reset email is not configured.")
    token = secrets.token_urlsafe(32)
    current = now(request)
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        uid = db.scalar(select(m.users.c.id).where(m.users.c.email == email))
        if uid:
            insert(
                db,
                m.password_reset_tokens,
                user_id=uid,
                token_hash=digest(token),
                expires_at=current + timedelta(minutes=30),
            )
            audit(db, request, uid, "request_password_reset", "account")
    if uid:
        link = f"{settings.public_url.rstrip('/')}/reset#token={token}"
        background.add_task(
            deliver_reset, provider, email, link, request.app.state.logger
        )
    return {"message": RESET_MESSAGE}


def deliver_reset(provider: EmailProvider, recipient: str, link: str, logger):
    try:
        provider.send(recipient, link)
    except (OSError, ValueError) as exc:
        logger.warning("password reset delivery failed: %s", type(exc).__name__)


def replace_password(db, uid, password, current):
    db.execute(
        m.users.update()
        .where(m.users.c.id == uid)
        .values(password_hash=hasher.hash(password))
    )
    db.execute(
        m.password_reset_tokens.update()
        .where(
            m.password_reset_tokens.c.user_id == uid,
            m.password_reset_tokens.c.used_at.is_(None),
        )
        .values(used_at=current)
    )
    db.execute(
        m.sessions.update().where(m.sessions.c.user_id == uid).values(revoked=True)
    )


@bootstrap.post("/confirm")
def confirm_reset(data: ResetConfirm, request: Request, response: Response):
    limit(request, "reset_confirm", request.app.state.settings.rate_login, 60)
    current = now(request)
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        uid = db.scalar(
            select(m.password_reset_tokens.c.user_id).where(
                m.password_reset_tokens.c.token_hash == digest(data.token),
                m.password_reset_tokens.c.expires_at > current,
                m.password_reset_tokens.c.used_at.is_(None),
            )
        )
        if not uid:
            raise HTTPException(400, "This password reset link is invalid or expired.")
        replace_password(db, uid, data.password, current)
        audit(db, request, uid, "reset_password", "account")
    clear_session(request, response)
    return {"ok": True}


def reauthenticate(db, uid, password):
    current_hash = db.scalar(select(m.users.c.password_hash).where(m.users.c.id == uid))
    if not current_hash or not verify(password, current_hash):
        raise HTTPException(403, "Current password is incorrect.")


@router.post("/account/password")
def change_password(
    data: ChangePassword, request: Request, response: Response, user: User
):
    uid = user["id"]
    limit(request, "password_change", request.app.state.settings.rate_login, 60, uid)
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        reauthenticate(db, uid, data.password)
        replace_password(db, uid, data.new_password, now(request))
        audit(db, request, uid, "change_password", "account")
    clear_session(request, response)
    return {"ok": True}


@router.delete("/account")
def delete_account(
    data: DeleteAccount, request: Request, response: Response, user: User
):
    uid = user["id"]
    limit(request, "delete_account", request.app.state.settings.rate_login, 60, uid)
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        reauthenticate(db, uid, data.password)
        audit(db, request, uid, "delete_account", "account")
        db.execute(m.users.delete().where(m.users.c.id == uid))
    clear_session(request, response)
    return {"ok": True}


@router.get("/audit")
def audit_entries(request: Request, user: User):
    with request.app.state.engine.connect() as db:
        return rows(
            db,
            select(
                m.audit_logs.c.id,
                m.audit_logs.c.action,
                m.audit_logs.c.object_type,
                m.audit_logs.c.outcome,
                m.audit_logs.c.created_at,
            )
            .where(m.audit_logs.c.user_ref == reference(request, user["id"]))
            .order_by(m.audit_logs.c.created_at.desc(), m.audit_logs.c.id.desc())
            .limit(100),
        )
