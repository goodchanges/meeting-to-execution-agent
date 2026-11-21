# Deployment

Build one instance from the repository root using `docker build -f deploy/Dockerfile --build-arg APP_VERSION=GIT_SHA -t meetflow:GIT_SHA .`. For local use, populate `.env` and run `docker compose -f deploy/docker-compose.yml up --build`. For staging, copy `deploy/staging.env.example` to ignored `deploy/staging.env`, set `GITHUB_REPOSITORY` to a private GitHub test repository and configure its dedicated `GITHUB_TOKEN` and separate staging credentials, and point `MEETFLOW_TAG` at the available git SHA image. Staging uses a separate volume.

Mount a persistent volume at `/data`, writable by UID/GID 10001, on a filesystem supporting SQLite WAL and hard links. Run one worker. Set proxy timeouts that allow bounded extraction to complete. Startup snapshots the existing database before changing its schema and runs Alembic.

Terminate TLS at the host or reverse proxy. Attach the chosen domain, set the hosting provider's requested DNS records, and wait for certificate issuance. Set `PUBLIC_URL` to the exact HTTPS origin, configure the proxy source IP in `TRUSTED_PROXIES`, and ensure the proxy overwrites `X-Forwarded-Proto`. Keep app ports private. Staging and production enable secure cookies and HSTS. Add explicit CORS origins only for separate authorized clients.

Check `/healthz`, `/readyz`, login, recent decisions, a signup verification email and a reset email and approval-to-GitHub flow before inviting users. Hosting, TLS, Docker startup and SMTP remain unverified.
