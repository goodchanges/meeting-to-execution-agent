# MeetFlow

**From Decisions to Execution.** Turn speaker-attributed meeting transcripts into reviewed decisions and tasks. Approved decisions become cross-meeting memory. Compare source evidence when decisions change and confirm GitHub posting separately from approval.

## Run locally

Use Python 3.11+, uv and Node 22 LTS (22.12+). From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
uv sync --locked
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
uv run alembic upgrade head
uv run uvicorn backend.app.main:app --no-access-log --no-proxy-headers
```

Open [MeetFlow](http://localhost:8000) and register. FastAPI serves the built UI. For hot reload run `npm --prefix frontend run dev` in a second terminal and add `http://127.0.0.1:5173` to `CORS_ORIGINS` for origin validation. On macOS/Linux use `cp` and `npm` in place of the PowerShell equivalents.

## Run the demo

Set `AI_MODE=demo` in `.env` before startup. Upload the [two supplied transcripts](samples/) in order. Fixture output is labeled **DEMO MODE — not live AI**. See the [demo walkthrough](docs/DEMO_WALKTHROUGH.md) for the sequence, dates, and GitHub setup.

| Settings | Purpose |
|---|---|
| `AI_MODE`, `LLM_API_KEY`, `LLM_MODEL` | OpenAI extraction uses a server key. Demo uses local fixtures. |
| `MAX_INPUT_TOKENS`, `MAX_OUTPUT_TOKENS`, `AI_TIMEOUT` | Input approximation, output limit and outbound timeout. |
| `AI_USER_MONTHLY_CALL_CAP`, `AI_GLOBAL_MONTHLY_CALL_CAP` | App-level paid attempt limits. The global aggregate survives account deletion. Configure provider budgets separately. |
| `GITHUB_TOKEN` | Server-only fine-grained PAT for one dedicated repository, with Issues read/write. Set its `owner/name` in Settings. |
| `DB_PATH`, `MAX_UPLOAD_BYTES`, `MAX_SEGMENTS` | SQLite and transcript limits. |
| `SCHEDULER_ENABLED`, `REMINDER_DAYS` | In-process scheduler and upcoming deadline window. |
| `PUBLIC_URL`, `APP_ENV`, `SECRET_KEY`, `CORS_ORIGINS`, `TRUSTED_PROXIES` | Environment, origins and TLS. Lists are JSON arrays. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_SENDER` | SMTP reset delivery via STARTTLS outside development. |
| `METRICS_TOKEN`, `BACKUP_DIR`, `BACKUP_RETAIN` | Optional metrics lock and snapshot retention. |

Runtime OpenAI billing is separate from Codex billing. Check pricing before enabling live AI. [GPT-6 Luna model reference](https://developers.openai.com/api/docs/models/gpt-6-luna)

## Verify and maintain

```powershell
uv run ruff check backend scripts evals
uv run mypy backend scripts evals
uv run pytest -q
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
uv run python -m evals.run_evals --provider fake
```

See the [Makefile](Makefile), [architecture](docs/ARCHITECTURE.md), [deployment](docs/DEPLOYMENT.md), [operations](docs/OPERATIONS.md), [rollback](docs/ROLLBACK.md), [security](docs/SECURITY.md), [dependency audit](docs/DEPENDENCY_AUDIT.md), and [implementation log](docs/IMPLEMENTATION_LOG.md).

Live evals not run. Automated checks use fixtures and mocked GitHub HTTP. Live GitHub, SMTP, hosted deployment, hosted GitHub Actions, and Docker rollback require separate verification. Draft [privacy](docs/PRIVACY_POLICY.md) and [terms](docs/TERMS_OF_SERVICE.md) require legal review before commercial use.
