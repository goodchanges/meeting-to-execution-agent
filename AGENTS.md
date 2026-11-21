# MeetFlow

Read this file, README.md, docs/IMPLEMENTATION_LOG.md and git status before resuming. Continue from the current working tree. Work in small vertical slices and use conventional commits on feat/meetflow-mvp. Keep one agent per working tree.

Use Python/FastAPI, uv, SQLAlchemy/SQLite/Alembic and React/TypeScript/Vite. Follow README commands from the repository root. Keep owner scoping, validation and approvals on the server. Prioritize the seven P0 workflows and run the two-meeting mocked integration test before operations polish.

Never commit or log secrets. Ship nothing externally without explicit approval. Mock GitHub and AI in automated tests. Runtime live AI requires explicit configuration and incurs separate provider charges. Label fixture-backed data DEMO MODE — not live AI. Report actual checks and mark unavailable checks NOT RUN. Keep the runtime single-instance and the implementation small.
