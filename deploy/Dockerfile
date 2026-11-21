FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.11.21 AS uv
FROM python:3.13-slim-bookworm AS runtime
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/app/.venv/bin:$PATH \
    DB_PATH=/data/meetflow.sqlite \
    BACKUP_DIR=/data/backups \
    PORT=8000
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY alembic.ini ./
COPY backend/ backend/
COPY scripts/ scripts/
COPY samples/ samples/
COPY --from=frontend /build/dist frontend/dist
RUN groupadd --gid 10001 meetflow && useradd --system --uid 10001 --gid 10001 meetflow \
    && install -d -o 10001 -g 10001 -m 0700 /data
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; port=os.getenv('PORT','8000'); assert urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=3).status == 200"
CMD ["python", "-m", "scripts.start"]
