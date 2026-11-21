import json
import logging
import re
from contextlib import asynccontextmanager
from time import monotonic
from uuid import uuid4

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from . import auth, meetings
from .ai import DemoProvider, LiveProvider
from .config import Settings
from .db import engine_for, utcnow
from .security import Limiter, limit

log = logging.getLogger("meetflow")


def create_app(settings: Settings | None = None, *, clock=utcnow, provider=None):
    settings = settings or Settings()
    engine = engine_for(settings.db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(
        title="MeetFlow",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.logger = log
    app.state.clock = clock
    app.state.provider = provider or (
        DemoProvider() if settings.ai_mode == "demo" else LiveProvider(settings)
    )
    app.state.limiter = Limiter()
    config = Config("alembic.ini")
    head = ScriptDirectory.from_config(config).get_current_head()

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(
            {"error_id": request.state.request_id, "message": str(exc.detail)},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = ", ".join(dict.fromkeys(str(e["loc"][-1]) for e in exc.errors()))
        return JSONResponse(
            {
                "error_id": request.state.request_id,
                "message": f"Invalid or missing field: {fields}.",
            },
            status_code=422,
        )

    @app.middleware("http")
    async def guard(request: Request, call_next):
        inbound = request.headers.get("x-request-id", "")
        request.state.request_id = (
            inbound if re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", inbound) else uuid4().hex
        )
        started = monotonic()
        try:
            scheme = request.url.scheme
            if request.client and request.client.host in settings.trusted_proxies:
                scheme = request.headers.get("x-forwarded-proto", scheme)
            if settings.secure and scheme != "https":
                target = settings.public_url.rstrip("/") + request.url.path
                response = RedirectResponse(target, status_code=307)
            else:
                if request.url.path.startswith("/api/"):
                    limit(request, "api", settings.rate_general, 60)
                    max_body = settings.max_upload_bytes + 65536
                    body = bytearray()
                    async for part in request.stream():
                        if len(body) + len(part) > max_body:
                            raise HTTPException(413, "Request exceeds the size limit.")
                        body.extend(part)
                    request._body = bytes(body)
                response = await call_next(request)
        except HTTPException as exc:
            response = await http_error(request, exc)
        except Exception as exc:  # noqa: BLE001 - return sanitized global error
            log.error(
                "request_id=%s exception=%s",
                request.state.request_id,
                type(exc).__name__,
            )
            response = JSONResponse(
                {
                    "error_id": request.state.request_id,
                    "message": "An unexpected error occurred.",
                },
                status_code=500,
            )
        response.headers.update(
            {
                "X-Request-ID": request.state.request_id,
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            }
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if settings.secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        route = request.scope.get("route")
        duration = round((monotonic() - started) * 1000, 2)
        log.info(
            json.dumps(
                {
                    "request_id": request.state.request_id,
                    "method": request.method,
                    "route": getattr(route, "path", "unmatched"),
                    "status": response.status_code,
                    "user_ref": getattr(request.state, "user_ref", None),
                    "duration_ms": duration,
                    "slow": duration >= settings.slow_request_ms,
                }
            )
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=[
            "Content-Type",
            "X-CSRF-Token",
            "X-MeetFlow-Client",
            "X-Request-ID",
        ],
    )
    app.include_router(meetings.protected)
    app.include_router(auth.bootstrap)
    app.include_router(auth.protected)

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/readyz")
    def readiness():
        try:
            with engine.connect() as db:
                db.execute(text("SELECT 1"))
                if MigrationContext.configure(db).get_current_revision() == head:
                    return {"status": "ok"}
        except SQLAlchemyError as exc:
            log.warning("readiness check failed: %s", type(exc).__name__)
        return JSONResponse({"status": "not-ready"}, status_code=503)

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Endpoint not found.")
        root = settings.frontend_dir.resolve()
        asset = (root / path).resolve()
        if not asset.is_relative_to(root):
            raise HTTPException(404, "Page not found.")
        if asset.is_file():
            return FileResponse(asset)
        if not path.startswith("assets/") and (root / "index.html").is_file():
            return FileResponse(root / "index.html")
        raise HTTPException(404, "Page not found.")

    return app


app = create_app()
