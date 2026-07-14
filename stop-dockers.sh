#!/usr/bin/env bash
# Stop all litgraph local dockers.
set -euo pipefail

cd "$(dirname "$0")"

docker compose -f infra/compose.yml \
  --profile core --profile redis-local --profile app --profile worker \
  --profile frontend-dev --profile frontend-prod down

echo ">> Stopped."
