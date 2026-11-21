import hashlib
import hmac
import secrets
from collections import deque
from datetime import timedelta
from threading import Lock
from time import monotonic

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException, Request, Response
from sqlalchemy import Connection, select

from .db import insert
from .models import audit_logs, sessions, users

hasher = PasswordHasher()
dummy_hash = hasher.hash(secrets.token_hex(32))
SESSION = "meetflow_session"
CSRF = "meetflow_csrf"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def reference(request: Request, value: str) -> str:
    key = request.app.state.settings.secret_key.get_secret_value().encode()
    return hmac.digest(key, value.encode(), "sha256").hex()


def verify(password: str, hash_value: str) -> bool:
    try:
        return hasher.verify(hash_value, password)
    except VerificationError:
        return False


def now(request: Request):
    return request.app.state.clock()


def audit(
    db: Connection,
    request: Request,
    user_id: str,
    action: str,
    object_type: str,
    object_id: str | None = None,
    outcome: str = "success",
):
    insert(
        db,
        audit_logs,
        user_ref=reference(request, user_id),
        action=action,
        object_type=object_type,
        object_id=object_id,
        outcome=outcome,
        request_id=request.state.request_id,
        ip_hash=reference(request, client_ip(request)),
        created_at=now(request),
        detail={},
    )


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class Limiter:
    def __init__(self):
        self.events: dict[str, deque[float]] = {}
        self.lock = Lock()

    def check(self, key: str, limit: int, seconds: int):
        with self.lock:
            current = monotonic()
            if len(self.events) >= 10_000:
                self.events = {
                    k: v for k, v in self.events.items() if v and v[-1] > current - 3600
                }
                if len(self.events) >= 10_000 and key not in self.events:
                    raise HTTPException(
                        429, "Too many requests.", headers={"Retry-After": "60"}
                    )
            events = self.events.setdefault(key, deque())
            while events and events[0] <= current - seconds:
                events.popleft()
            if len(events) >= limit:
                retry = max(1, int(events[0] + seconds - current) + 1)
                raise HTTPException(
                    429, "Too many requests.", headers={"Retry-After": str(retry)}
                )
            events.append(current)


def limit(
    request: Request, route: str, count: int, seconds: int, identity: str | None = None
):
    limiter = request.app.state.limiter
    limiter.check(f"{route}:ip:{client_ip(request)}", count, seconds)
    if identity:
        limiter.check(f"{route}:id:{identity}", count, seconds)


def bootstrap_csrf(request: Request):
    origin = request.headers.get("origin")
    settings = request.app.state.settings
    if origin and origin not in {
        settings.public_url.rstrip("/"),
        *settings.cors_origins,
    }:
        raise HTTPException(403, "Origin is not allowed.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Origin is not allowed.")
    if request.headers.get("x-meetflow-client") != "1":
        raise HTTPException(403, "Client header required.")


def start_session(db: Connection, request: Request, response: Response, user_id: str):
    session_token, csrf_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    settings = request.app.state.settings
    lifetime = timedelta(hours=settings.session_hours)
    current = now(request)
    insert(
        db,
        sessions,
        user_id=user_id,
        token_hash=digest(session_token),
        csrf_hash=digest(csrf_token),
        created_at=current,
        expires_at=current + lifetime,
        last_seen=current,
        revoked=False,
    )
    for key, value in ((SESSION, session_token), (CSRF, csrf_token)):
        response.set_cookie(
            key,
            value,
            httponly=key == SESSION,
            secure=settings.secure,
            samesite="lax",
            max_age=int(lifetime.total_seconds()),
        )


def clear_session(request: Request, response: Response):
    for key in (SESSION, CSRF):
        response.delete_cookie(
            key,
            secure=request.app.state.settings.secure,
            httponly=key == SESSION,
            samesite="lax",
        )


def current_user(request: Request, response: Response) -> dict:
    token = request.cookies.get(SESSION, "")
    if not token or len(token) > 128:
        raise HTTPException(401, "Sign in to continue.")
    current = now(request)
    with request.app.state.engine.begin() as db:
        session = (
            db.execute(
                select(sessions).where(
                    sessions.c.token_hash == digest(token),
                    sessions.c.revoked.is_(False),
                    sessions.c.expires_at > current,
                )
            )
            .mappings()
            .first()
        )
        if not session:
            raise HTTPException(401, "Sign in to continue.")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            bootstrap_csrf(request)
            csrf = request.headers.get("x-csrf-token", "")
            cookie = request.cookies.get(CSRF, "")
            if (
                not csrf
                or not cookie
                or len(csrf) > 128
                or not csrf.isascii()
                or not cookie.isascii()
                or not hmac.compare_digest(cookie, csrf)
                or not hmac.compare_digest(session["csrf_hash"], digest(csrf))
            ):
                raise HTTPException(403, "Invalid CSRF token.")
        user = dict(
            db.execute(select(users).where(users.c.id == session["user_id"]))
            .mappings()
            .one()
        )
        if current - session["last_seen"] > timedelta(minutes=15):
            settings = request.app.state.settings
            lifetime = timedelta(hours=settings.session_hours)
            db.execute(
                sessions.update()
                .where(sessions.c.id == session["id"])
                .values(
                    last_seen=current,
                    expires_at=current + lifetime,
                )
            )
            for key in (SESSION, CSRF):
                if request.cookies.get(key):
                    response.set_cookie(
                        key,
                        request.cookies[key],
                        httponly=key == SESSION,
                        secure=settings.secure,
                        samesite="lax",
                        max_age=int(lifetime.total_seconds()),
                    )
    request.state.session_id = session["id"]
    request.state.user_ref = reference(request, user["id"])
    return user
