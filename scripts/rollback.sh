#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 2 || ! "$1" =~ ^[0-9a-f]{7,40}$ || "$2" != https://* ]]; then
  echo "Usage: scripts/rollback.sh PREVIOUS_GIT_SHA HTTPS_PUBLIC_URL" >&2
  exit 2
fi
cd "$(dirname "$0")/.."
export MEETFLOW_TAG="$1"
docker compose -f deploy/docker-compose.staging.yml up -d --no-build
for attempt in {1..20}; do
  if curl -fsS --max-time 4 "${2%/}/readyz" >/dev/null; then
    echo "Previous image is responding at /readyz. Verify login and data access."
    exit 0
  fi
  sleep 3
done
echo "Readiness check failed." >&2
exit 1
