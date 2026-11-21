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
from .auth import bootstrap as auth_bootstrap
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
    start_session,
    verify,
)

bootstrap = APIRouter(prefix="/api/auth/reset", dependencies=[Depends(bootstrap_csrf)])
router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
RESET_MESSAGE = "If the account exists and email delivery is available, a reset link will arrive shortly."
SIGNUP_MESSAGE = "If this email is eligible, a registration link will arrive shortly."
EmailToken = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{43}$")]


class EmailRequest(BaseModel):
    email: EmailStr


class ResetConfirm(BaseModel):
    token: EmailToken
    password: Password


class SignupConfirm(ResetConfirm):
    display_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]


class Reauth(BaseModel):
    password: Annotated[str, StringConstraints(max_length=128)]


class ChangePassword(Reauth):
    new_password: Password


class DeleteAccount(Reauth):
    confirmation: Literal["DELETE"]


class EmailProvider(Protocol):
    def send(self, recipient: str, link: str, subject: str) -> None: ...


class DevOutboxEmailProvider:
    def __init__(self, directory: Path):
        self.directory = directory

    def send(self, recipient: str, link: str, subject: str):
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"{uuid4().hex}.txt").write_text(
            f"To: {recipient}\nSubject: {subject}\n\n{link}\n",
            encoding="utf-8",
        )


class SmtpEmailProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, recipient: str, link: str, subject: str):
        settings = self.settings
        message = EmailMessage()
        message["From"] = settings.smtp_sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(f"Use this link within 30 minutes:\n{link}")
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


@auth_bootstrap.post("/register", status_code=202)
def request_signup(data: EmailRequest, request: Request, background: BackgroundTasks):
    settings = request.app.state.settings
    email = data.email.casefold()
    limit(request, "register", settings.rate_login, 60, reference(request, email))
    provider = request.app.state.email
    if not provider:
        raise HTTPException(503, "Registration email is not configured.")
    token = secrets.token_urlsafe(32)
    current = now(request)
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        db.execute(
            m.registration_tokens.delete().where(
                m.registration_tokens.c.expires_at <= current
            )
        )
        existing = db.scalar(select(m.users.c.id).where(m.users.c.email == email))
        if not existing:
            db.execute(
                m.registration_tokens.insert().values(
                    token_hash=digest(token),
                    email=email,
                    expires_at=current + timedelta(minutes=30),
                )
            )
    if not existing:
        link = f"{settings.public_url.rstrip('/')}/register/confirm#token={token}"
        background.add_task(
            deliver_link,
            provider,
            email,
            link,
            "Confirm your MeetFlow registration",
            request.app.state.logger,
        )
    return {"message": SIGNUP_MESSAGE}


@auth_bootstrap.post("/register/confirm", status_code=201)
def confirm_signup(data: SignupConfirm, request: Request, response: Response):
    limit(request, "register_confirm", request.app.state.settings.rate_login, 60)
    current = now(request)
    password_hash = hasher.hash(data.password)
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        email = db.scalar(
            select(m.registration_tokens.c.email).where(
                m.registration_tokens.c.token_hash == digest(data.token),
                m.registration_tokens.c.expires_at > current,
            )
        )
        if not email or db.scalar(select(m.users.c.id).where(m.users.c.email == email)):
            raise HTTPException(400, "This registration link is invalid or expired.")
        user_id = insert(
            db,
            m.users,
            email=email,
            password_hash=password_hash,
            display_name=data.display_name,
            created_at=current,
        )
        insert(db, m.app_settings, user_id=user_id, timezone="Asia/Kolkata")
        db.execute(
            m.registration_tokens.delete().where(m.registration_tokens.c.email == email)
        )
        audit(db, request, user_id, "register", "account")
        start_session(db, request, response, user_id)
    return {"id": user_id, "display_name": data.display_name}


@bootstrap.post("/request")
def request_reset(data: EmailRequest, request: Request, background: BackgroundTasks):
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
            deliver_link,
            provider,
            email,
            link,
            "Reset your MeetFlow password",
            request.app.state.logger,
        )
    return {"message": RESET_MESSAGE}


def deliver_link(
    provider: EmailProvider, recipient: str, link: str, subject: str, logger
):
    try:
        provider.send(recipient, link, subject)
    except (OSError, ValueError) as exc:
        logger.warning("account email delivery failed: %s", type(exc).__name__)


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
