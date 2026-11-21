# Operations

Point an uptime monitor at `/healthz`. Use `/readyz` to check connectivity and the Alembic head. Request logs carry IDs, route templates, status, duration, keyed user references and a slow flag. Enable optional JSON metrics with `METRICS_TOKEN` and send it as a bearer header. Route percentiles retain up to 512 recent samples, excluding the extraction endpoint. AI totals track token counts, latency and outcomes separately. Request counters reset on restart.

## Backups

Run `uv run python -m scripts.backup` with `DB_PATH`, `BACKUP_DIR` and `BACKUP_RETAIN`. The default keeps 14 snapshots. SQLite's online backup API supports active WAL traffic. Configure and test encrypted off-host copies with restricted access.

Run `uv run python -m scripts.verify_restore SNAPSHOT` to rehearse and verify counts and foreign keys. Use `uv run python -m scripts.restore SNAPSHOT NEW_DB_PATH` for a real recovery. Stop writers, preserve the old database, repoint `DB_PATH` and smoke test before opening ingress. Deleted user data remains in old snapshots until retention expires. Reapply outstanding deletion requests when restoring an older snapshot.

## Schedules, latency and spend

The scheduler checks reminders each minute and generates weekly digests during the Monday 09:00 local hour. After downtime, use **Generate now**. Scheduling and rate limits are per-process.

The target is p95 under 300 ms for key non-AI requests. Measure with `uv run python -m scripts.measure_perf` on its own disposable development instance, with no concurrent traffic. Point the script and app at the same `DEV_OUTBOX` for synthetic signup. It writes actual counts and timing to ignored `data/performance.json`.

Set provider-side spend limits and billing alerts manually. Keep a dedicated project and rotate OpenAI, GitHub and SMTP credentials as needed. Runtime AI uses separate billing from Codex. Manual live evals use their own call and estimated spend limits.
