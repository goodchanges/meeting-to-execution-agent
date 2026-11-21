# Demo walkthrough

1. Set `AI_MODE=demo`. Register using the link in the development outbox, then upload `samples/meeting1_2026-11-18.txt` as **Launch kickoff**. Leave the date blank to read it from the filename. Select **Extract decisions and tasks**.
2. In **Review center**, approve the Dec 15 launch decision, the authentication requirement and Sarah and Rahul's tasks. Check **Decision memory**.
3. Upload and process `samples/meeting2_2026-11-20.vtt` as **Launch follow-up**. Compare both sources in **Conflict center**. Launch is **Supersedes**. Authentication is **Consistent**. Choose **Accept replacement**, confirm, and then approve Alex's checklist in **Review center**.
4. If you have set `GITHUB_REPOSITORY` and a matching dedicated `GITHUB_TOKEN` on the server, open **Action items**, choose **Create GitHub issue**, check the destination and click **Confirm post**. The issue URL appears after GitHub confirms it. Without a token, show the confirmation form and configuration status.
5. In **Notifications**, select **Generate reminders now**. The automated test injects Dec 3, 2026 so Alex is due soon and Sarah and Rahul are overdue. The UI uses current time in the account timezone.
6. In **Weekly digests**, click **Generate now**. Inspect the entries for Alex, Sarah and Rahul. Return to memory to see both launch decisions and the replacement link.

To preseed the first meeting at the review step, stop the app and set `APP_ENV=development`, `AI_MODE=demo` and `DB_PATH=data/demo.sqlite`. Run `make demo-reset` or `uv run python -m scripts.demo_reset`. The command prompts for a password and resets only the dedicated demo account in that database. Restart with the same settings.

Run `uv run pytest -q backend/tests/test_two_meetings.py` to repeat the workflow through the API with fixture AI, mocked GitHub HTTP and the Dec 3 clock.
