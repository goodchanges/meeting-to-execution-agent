# Dependency and secret scans

2026-11-21, local Windows workspace.

| Check | Outcome |
|---|---|
| `uv export --locked --no-dev --no-emit-project -o data/audit-requirements.txt` | Exported pinned runtime requirements with hashes. |
| `uv run pip-audit --disable-pip --require-hashes -r data/audit-requirements.txt` | No known vulnerabilities found in the audited Python runtime dependencies. |
| `npm audit --audit-level=high` in `frontend/` | Found 0 vulnerabilities. |
| Gitleaks 8.30.1 `git --redact --no-banner .` | No leaks found in local Git history. |

No findings were accepted in these runs. Results reflect the package locks, available advisory data and scan coverage at execution time. GitHub Actions, Docker image dependencies and infrastructure have separate verification requirements.
