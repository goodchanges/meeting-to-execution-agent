# Deployment

Build one instance from the repository root using `docker build -f deploy/Dockerfile --build-arg APP_VERSION=GIT_SHA -t meetflow:GIT_SHA .`. For local use, populate `.env` and run `docker compose -f deploy/docker-compose.yml up --build`. For staging, copy `deploy/staging.env.example` to ignored `deploy/staging.env`, set `GITHUB_REPOSITORY` to a private GitHub test repository and configure its dedicated `GITHUB_TOKEN` and separate staging credentials, and point `MEETFLOW_TAG` at the available git SHA image. Staging uses a separate volume.

Mount a persistent volume at `/data`, writable by UID/GID 10001, on a filesystem supporting SQLite WAL and hard links. Run one worker. Set proxy timeouts that allow bounded extraction to complete. Startup snapshots the existing database before changing its schema and runs Alembic.

For a local development container, read a synthetic signup link with `docker compose -f deploy/docker-compose.yml exec meetflow ls -t /data/dev-outbox`, then open the corresponding file with `docker compose -f deploy/docker-compose.yml exec meetflow cat /data/dev-outbox/FILENAME`.

Terminate TLS at the host or reverse proxy. Attach the chosen domain, set the hosting provider's requested DNS records, and wait for certificate issuance. Set `PUBLIC_URL` to the exact HTTPS origin, configure the proxy source IP in `TRUSTED_PROXIES`, and ensure the proxy overwrites `X-Forwarded-Proto`. Keep app ports private. Staging and production enable secure cookies and HSTS. Add explicit CORS origins only for separate authorized clients.

Check `/healthz`, `/readyz`, login, recent decisions, a signup verification email and a reset email and approval-to-GitHub flow before inviting users. Hosting, TLS, Docker startup and SMTP remain unverified.

## Render prototype

Use one paid Docker web service with the repository root as the build context and `deploy/Dockerfile` as the Dockerfile path. Mount a persistent disk at `/data` and use `/readyz` for the health check. The first rollout can use the service's HTTPS subdomain. [Render web services](https://render.com/docs/web-services) · [Persistent disks](https://render.com/docs/disks)

- Set `APP_ENV=staging`, `PUBLIC_URL` to the HTTPS service origin, and a strong `SECRET_KEY` in the host's environment. Verify the ingress peer and its forwarded protocol behavior before configuring `TRUSTED_PROXIES`. Check that the homepage loads over HTTPS without a redirect loop and that signup sets secure cookies.
- Configure the signup and reset mail sender through SMTP with STARTTLS. Confirm receipt of both messages using a test mailbox. Render's free web services block port 587. [Render's SMTP restrictions](https://render.com/docs/free)
- Start in demo mode for the hosted infrastructure check. After the approved synthetic Gemini smoke test passes, supply `GEMINI_API_KEY` through the host's secret settings, set `AI_PROVIDER=gemini` and `AI_MODE=live`, and verify the hosted application with synthetic input before accepting real transcripts. Set the app's monthly AI call caps and provider billing limits for the intended rollout.
