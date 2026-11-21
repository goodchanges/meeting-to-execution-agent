# Demo walkthrough

Install dependencies and build the frontend using the README setup commands. For an isolated demo alongside an existing checkout, run these commands in PowerShell 7.5 or later. This PowerShell version preserves an empty environment variable, which overrides any GitHub token in the existing `.env`.

```powershell
$env:APP_ENV = 'development'
$env:AI_MODE = 'demo'
$env:DB_PATH = 'data/walkthrough.sqlite'
$env:DEV_OUTBOX = 'data/walkthrough-outbox'
$env:PUBLIC_URL = 'http://localhost:8001'
$env:GITHUB_TOKEN = ''
$env:REMINDER_DAYS = '30'
uv run alembic upgrade head
uv run uvicorn backend.app.main:app --port 8001 --no-access-log --no-proxy-headers
```

On a fresh checkout, the regular README startup with `.env.example` also works. Keep `GITHUB_TOKEN` blank and set `REMINDER_DAYS=30` for this walkthrough. The demo uses the two local fixtures and requires no AI credentials.

1. Open [the isolated MeetFlow demo](http://localhost:8001), or use port 8000 for the regular README startup. Create a workspace using the registration link in the development outbox. From **Upload transcript**, download both demo transcripts. Upload the TXT file as **Launch kickoff**. Leave the date blank to read it from the filename. Select **Extract decisions and tasks**.
2. In **Review center**, approve the Dec 15 launch decision, the authentication requirement and Sarah and Rahul's tasks. Check **Decision memory**.
3. Upload and process `samples/meeting2_2026-11-20.vtt` as **Launch follow-up**. Compare both sources in **Conflict center**. Launch is **Supersedes**. Authentication is **Consistent**. Choose **Accept replacement**, confirm, and then approve Alex's checklist in **Review center**.
4. In **Action items**, select **Create GitHub issue** on Alex's approved task and inspect the confirmation. With the token blank, **Confirm post** is disabled. A separately configured live GitHub flow publishes only after explicit confirmation.
5. In **Notifications**, select **Generate reminders now**. The UI uses the current date in the account timezone and displays overdue tasks and tasks due within the configured window. The 30-day setting makes all three fixture tasks visible from Nov 5, 2026 onward. The automated test uses a two-day window and a Dec 3, 2026 clock, so Alex is due soon and Sarah and Rahul are overdue.
6. In **Weekly digests**, click **Generate now**. Inspect the entries for Alex, Sarah and Rahul. Return to memory to see both launch decisions and the replacement link.

To preseed the first meeting at the review step, stop the app and set `APP_ENV=development`, `AI_MODE=demo` and `DB_PATH=data/demo.sqlite`. Run `make demo-reset` or `uv run python -m scripts.demo_reset`. The command prompts for a password and resets only the dedicated demo account in that database. Restart with the same settings.

Run `uv run pytest -q backend/tests/test_two_meetings.py` to repeat the workflow through the API with fixture AI, mocked GitHub HTTP and the Dec 3 clock.
