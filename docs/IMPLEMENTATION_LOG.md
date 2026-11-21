# Implementation log

## 2026-11-21 — Inspection

Workspace was empty, with no Git history, README, application or dependency files. Python, uv, Node, npm and Git were detected. Docker and gitleaks were not found on PATH.

Plan: establish migrated SQLite and authenticated routes, implement ingestion and memory, add approval and execution, then build the UI and verify the two-meeting flow before operations work.

## 2026-11-21 — Backend core

Added migrated SQLite, session auth, transcript ingestion and schema-validated AI with durable evidence and scoped memory. Fresh migration, readiness, anonymous account rejection and registration smoke returned 200/401/201. Next: approval, execution and fixtures.

## 2026-11-21 — Execution workflow

Added review and conflict state transitions, issue reconciliation, reminders and weekly digests. The automated two-meeting scenario passed with fixture-backed AI and GitHub HTTP mocked. Next: frontend and security completion.

## 2026-11-21 — Frontend and security

Built responsive workspace, transcript upload, review, conflict comparison, action confirmation, digest and settings pages. Edge smoke passed registration, TXT and VTT uploads, extraction, approval, conflict resolution, decision memory, digest generation and mobile navigation. Added reset, reauthentication, cascade deletion, rate limits, global call accounting and security checks. Next: close out quality and operations.

## 2026-11-21 — Quality, operations and verification

Backend: 38 pytest cases passed, including the two-meeting workflow, scheduled digest callback, coverage of protected routes, account cleanup, mocked provider failures and pre- and post-migration backup restores. Ruff and mypy passed. Frontend: npm ci, ESLint, TypeScript, 2 Vitest cases and Vite build passed. Fake eval: 24/24. pip-audit and npm audit reported no known findings. A pre-migration snapshot was restored and verified against its schema revision. The demo-reset command was exercised twice using a generated test password. Sequential local HTTP performance on a disposable database: 25 samples per endpoint, p95 2.84–4.18 ms. GitHub CI, Docker build and rollback, live provider calls, SMTP and deployment were not run.

## 2026-11-21 — GitHub routing, undated tasks and signup privacy

Pinned all outbound issue requests to GITHUB_REPOSITORY. Account Settings displays that destination read-only. Legacy issue attempts that target a different or unknown repository stop for operator reconciliation. Added explicit no-deadline confirmation, retained review for ambiguous dates, and handled undated tasks in issues, reminders and digests. Public registration returns a generic 202 without cookies and uses a single-use email link before account creation. Alembic 0003 adds the signup token table and deadline flag.

Verified locally: 55 pytest cases passed, including the two-meeting integration test rerun separately. Ruff and mypy passed. npm test passed 2 cases, and ESLint and Vite build passed. Offline evals passed 24/24. Edge confirmed signup through the development outbox and the read-only repository. pip-audit and npm audit reported no known vulnerabilities in their audited sets. Gitleaks found no leaks. Live OpenAI, GitHub, SMTP and deployment were NOT RUN.

## 2026-11-21 — DeepSeek Responses API

Reused the live provider interface with the DeepSeek /responses endpoint, deepseek-flash model and DEEPSEEK_API_KEY. Native json_schema is the default. The separate OpenAI strict flag is undocumented for DeepSeek. JSON Object mode offers an explicit fallback and supplies the schema in the instructions. Both paths enforce strict Pydantic validation and reject incomplete outputs.

Verified 62 pytest cases, the separately rerun two-meeting integration test, Ruff, mypy, 2 Vitest cases, ESLint, the frontend build, and 24/24 offline eval cases. The adapter tests exercised extraction, owners, deadlines and cross-meeting comparisons in both format modes with mocked upstream responses. The DeepSeek key is still missing, so authenticated model metadata and paid validation are NOT RUN. The local runtime remains in demo mode.

## 2026-11-21 — Gemini Interactions API

Set Gemini as the default live provider. The retained DeepSeek adapter is selectable through AI_PROVIDER. Gemini uses google-genai 2.34.0 and gemini-3.8-flash, a stateless Interactions request, native JSON Schema output, and the original Pydantic validation. Requests have one SDK attempt and no automatic continuation. The local masked setup and metadata-only check do not change AI_MODE or existing environment values.

Verified 70 pytest cases, the separate two-meeting rerun, 24/24 fake eval cases, Ruff, mypy, 2 Vitest cases, ESLint and the frontend build. The SDK adapter and metadata transport were exercised offline with mocked HTTP. Runtime pip-audit reported no known vulnerabilities. Gemini key setup is ready. Authenticated metadata and Gemini generation were NOT RUN.

## 2026-11-21 — Local demo release check

Made README setup preserve an existing `.env`. Documented a separate demo database, port and outbox, a 30-day reminder window for the fixtures, and a GitHub confirmation preview with posting disabled. Set the container's default development outbox under the writable `/data` volume. Moved the empty GitHub token placeholder away from the next assignment to clear a Gitleaks false positive.

From a clean source snapshot, installed locked dependencies and ran 70 backend tests, Ruff, mypy, 24/24 fake evals, and frontend lint, typecheck, 2 Vitest tests and production build on Node 22.23.5. The dedicated two-meeting integration test passed with mocked GitHub HTTP. Edge passed fresh migrations, health and readiness, local email signup, both fixture extractions, approvals, decision replacement and memory, the disabled GitHub confirmation, all three reminders and digests, and mobile navigation. pip-audit and npm audit reported no known vulnerabilities. Gitleaks found no findings in Git history or the checked source snapshot after the placeholder change.

The local Gemini metadata check succeeded. The ignored smoke harness now captures sanitized transport exception types and numeric codes, verified with offline DNS, TLS and timeout fixtures. Live generation, live GitHub, hosted deployment and container startup were NOT RUN. The normal application remained in demo mode.

## 2026-11-21 — Final local release verification

Upgraded ESLint to 10.15.0 and its recommended configuration package to 10.0.1. The existing plugins and configuration passed on Node 22.23.5. Added httpx2 2.16.2 to the development dependency group. FastAPI 0.165.0 and Starlette 1.10.0 use it for TestClient. Production integrations retain HTTPX.

Passed 70 backend tests with warnings treated as errors, the separately rerun two-meeting test, Ruff, mypy and 24/24 offline evaluations. A clean frontend install, ESLint, TypeScript, 2 Vitest tests and the production frontend build passed. Edge passed the two-meeting fixture walkthrough again on a fresh database. pip-audit reported no known vulnerabilities in the runtime and development requirements, and npm audit reported zero. Gitleaks found no findings in the full local Git history or the final source snapshot.

The existing `.env` remained byte-for-byte unchanged, ignored and untracked. The local application and fresh-checkout example both use demo mode. Live generation, GitHub posting, external notifications, Docker startup and hosted deployment were NOT RUN.
