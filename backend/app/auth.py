from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, StringConstraints
from sqlalchemy import select

from .models import sessions, users
from .security import (
    audit,
    bootstrap_csrf,
    clear_session,
    current_user,
    dummy_hash,
    limit,
    reference,
    start_session,
    verify,
)

bootstrap = APIRouter(prefix="/api/auth", dependencies=[Depends(bootstrap_csrf)])
protected = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
User = Annotated[dict, Depends(current_user)]
Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]


class Credentials(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(max_length=128)]


@bootstrap.post("/login")
def login(data: Credentials, request: Request, response: Response):
    email = data.email.casefold()
    limit(
        request,
        "login",
        request.app.state.settings.rate_login,
        60,
        reference(request, email),
    )
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        user = (
            db.execute(select(users).where(users.c.email == email)).mappings().first()
        )
        valid = verify(data.password, user["password_hash"] if user else dummy_hash)
        if user and valid:
            start_session(db, request, response, user["id"])
            audit(db, request, user["id"], "login", "account")
            return {"id": user["id"], "display_name": user["display_name"]}
        audit(
            db,
            request,
            user["id"] if user else "anonymous",
            "login",
            "account",
            outcome="failed",
        )
    raise HTTPException(401, "Email or password is incorrect.")


@protected.post("/auth/logout")
def logout(request: Request, response: Response, user: User):
    with request.app.state.engine.begin() as db:
        db.execute(
            sessions.update()
            .where(
                sessions.c.id == request.state.session_id,
                sessions.c.user_id == user["id"],
            )
            .values(revoked=True)
        )
        audit(db, request, user["id"], "logout", "account")
    clear_session(request, response)
    return {"ok": True}


@protected.get("/account")
def account(user: User, request: Request):
    settings = request.app.state.settings
    api_key = (
        settings.gemini_api_key
        if settings.ai_provider == "gemini"
        else settings.deepseek_api_key
    )
    return {
        "id": user["id"],
        "display_name": user["display_name"],
        "email": user["email"],
        "ai_mode": settings.ai_mode,
        "ai_provider": settings.ai_provider,
        "ai_ready": settings.ai_mode == "demo" or bool(api_key.get_secret_value()),
    }
