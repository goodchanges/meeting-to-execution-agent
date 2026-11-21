# MeetFlow

**From Decisions to Execution.** Turn speaker-attributed meeting transcripts into reviewed decisions and tasks. Approved decisions become cross-meeting memory. Compare source evidence when decisions change and confirm GitHub posting separately from approval.

## Run locally

Use Python 3.11+, uv and Node 22 LTS (22.13+). From the repository root in PowerShell:

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
uv sync --locked
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
uv run alembic upgrade head
uv run uvicorn backend.app.main:app --no-access-log --no-proxy-headers
```

On macOS or Linux, use `test -f .env || cp .env.example .env` for the first line and use `npm` in place of `npm.cmd`.

Open [MeetFlow](http://localhost:8000) and select **Create a workspace**. In development, open the registration link from the new file in the ignored `dev-outbox/` directory, then choose a display name and password. Existing users can sign in directly. FastAPI serves the built UI. For hot reload run `npm.cmd --prefix frontend run dev` in a second terminal and add `http://127.0.0.1:5173` to `CORS_ORIGINS` for origin validation.

## Run the demo

Set `AI_MODE=demo` in `.env` before startup. Download the [two supplied transcripts](samples/) from **Upload transcript** and process them in order. Fixture output is labeled **DEMO MODE — not live AI**. Local signup uses the development outbox and the demo requires no API keys. See the [demo walkthrough](docs/DEMO_WALKTHROUGH.md) for an isolated database, the reminder window, and the GitHub confirmation preview.

| Settings | Purpose |
|---|---|
| `AI_MODE`, `AI_PROVIDER`, `GEMINI_API_KEY`, `GEMINI_MODEL` | The demo uses local fixtures. The optional Gemini adapter targets the native Interactions API with `gemini-3.8-flash` by default. |
| `DEEPSEEK_API_KEY`, `LLM_MODEL`, `DEEPSEEK_OUTPUT_FORMAT` | Select `AI_PROVIDER=deepseek` to use DeepSeek explicitly. Its `/responses` adapter defaults to `deepseek-flash` and `json_schema`, with `json_object` available. |
| `MAX_INPUT_TOKENS`, `MAX_OUTPUT_TOKENS`, `AI_TIMEOUT` | Input approximation, output limit and outbound timeout. |
| `AI_USER_MONTHLY_CALL_CAP`, `AI_GLOBAL_MONTHLY_CALL_CAP` | App-level paid attempt limits. The global aggregate survives account deletion. Configure provider budgets separately. |
| `GITHUB_REPOSITORY`, `GITHUB_TOKEN` | Server-only `owner/repository` and a fine-grained PAT scoped to that same repository with Issues read/write. Settings displays the destination read-only. |
| `DB_PATH`, `MAX_UPLOAD_BYTES`, `MAX_SEGMENTS` | SQLite and transcript limits. |
| `SCHEDULER_ENABLED`, `REMINDER_DAYS` | In-process scheduler and upcoming deadline window. |
| `PUBLIC_URL`, `APP_ENV`, `SECRET_KEY`, `CORS_ORIGINS`, `TRUSTED_PROXIES` | Environment, origins and TLS. Lists are JSON arrays. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_SENDER` | SMTP signup and reset delivery via STARTTLS outside development. |
| `METRICS_TOKEN`, `BACKUP_DIR`, `BACKUP_RETAIN` | Optional metrics lock and snapshot retention. |

Gemini model metadata and authentication have been verified. Live generation remains unverified. The adapter's stateless Interactions requests, JSON Schema output and Pydantic validation are covered by offline tests with mocked responses. [Google Interactions API](https://ai.google.dev/gemini-api/docs/interactions), [structured output](https://ai.google.dev/gemini-api/docs/structured-output)

Tasks with an owner can be approved without a date after the reviewer edits the task and checks **Confirm no deadline was specified**. Ambiguous source deadlines require a date. Approved undated tasks appear in weekly digests and are skipped by deadline reminders.

Existing installations should run `uv run alembic upgrade head` before restarting. For an issue attempt already in progress or failed, MeetFlow reconciles against the configured repository only when it matches the recorded attempt. If it differs, have an operator check the original attempt before taking further action.

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

Automated checks use fixtures and mocked GitHub HTTP. Container startup, hosted deployment, hosted GitHub Actions, live GitHub and SMTP remain unverified. Draft [privacy](docs/PRIVACY_POLICY.md) and [terms](docs/TERMS_OF_SERVICE.md) require legal review before commercial use.
