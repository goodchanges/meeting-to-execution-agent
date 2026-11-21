.PHONY: install dev test lint typecheck build audit eval backup demo-reset
install:
	uv sync --locked
	npm --prefix frontend ci
dev:
	uv run alembic upgrade head
	uv run uvicorn backend.app.main:app --reload --no-access-log --no-proxy-headers
test:
	uv run pytest -q
	npm --prefix frontend test
lint:
	uv run ruff check backend scripts evals
	npm --prefix frontend run lint
typecheck:
	uv run mypy backend scripts evals
	npm --prefix frontend run typecheck
build:
	npm --prefix frontend run build
audit:
	uv export --locked --no-dev --no-emit-project -o data/audit-requirements.txt
	uv run pip-audit --disable-pip --require-hashes -r data/audit-requirements.txt
	npm --prefix frontend audit --audit-level=high
eval:
	uv run python -m evals.run_evals --provider fake
backup:
	uv run python -m scripts.backup
demo-reset:
	uv run python -m scripts.demo_reset
