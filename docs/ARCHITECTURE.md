# Architecture

One FastAPI process serves React and the authenticated API. SQLite uses WAL and foreign keys. Alembic owns schema changes. SQLAlchemy Core queries share owner filters and 404 handling. Mutation endpoints validate origin and a session-bound double-submit CSRF token.

1. Upload commits the source, hash, cue segments and participants.
2. Processing claims the meeting, extracts structured records and compares approved memory. Candidate search ranks up to 1,000 recent approved records by normalized subject key, topic and Jaccard overlap. It compares at most eight by default. Failed processing preserves source. Interrupted attempts can be reclaimed after 15 minutes. An explicit replacement can clear unreviewed proposals. Reviewed or edited records require a new upload to preserve history.
3. Proposals await human review. A previous decision remains active until blocking comparisons have resolutions. Replacement records link to the new decision while preserving history.
4. Issue creation requires separate confirmation after approval. Pending blocking comparisons in the same meeting block posting. A conditional claim precedes the API call. Retries check for a hidden marker and retain the originally claimed repository.
5. The scheduler creates unique reminders and uses one digest row per participant and week. Both jobs have authenticated manual triggers.

Evidence matching uses normalized substring checks. Owners are mapped to parsed speaker names when supported by the evidence. Relative dates use stable calendar rules. Candidate selection and model classification can miss changes. Processing compares against a snapshot of approved memory taken when it starts.

GitHub is outside the database transaction. Retries reconcile using a bounded ten-page scan that may need manual intervention. Provider delays, changed markers, and deleted issues affect duplicate detection.

One app instance owns the scheduler and rate limits. For PostgreSQL, use expand-only migrations, replace SQLite locks and upserts with PostgreSQL equivalents, validate UTC and FK behavior, add scheduler leadership if scaling out, copy data in FK order, and verify counts and references before cutover.
