#!/usr/bin/env bash
# Starter for all litgraph local dockers.
# Usage: ./start-dockers.sh [gpu]
#   no arg  -> CPU stack (dev)
#   gpu     -> GPU stack (dev)
set -euo pipefail

cd "$(dirname "$0")"

COMPOSE="docker compose -f infra/compose.yml"
if [ "${1:-}" = "gpu" ]; then
  COMPOSE="$COMPOSE -f infra/compose.gpu.yml"
fi

PROFILES="--profile core --profile redis-local --profile app --profile worker --profile frontend-dev"

echo ">> Starting litgraph dockers (${1:-cpu})..."
$COMPOSE $PROFILES up -d --wait --wait-timeout 120

echo ">> Status:"
$COMPOSE ps

echo
echo ">> Ready:"
echo "   frontend : http://localhost:5173"
echo "   api      : http://localhost:8889"
echo "   mcp      : http://localhost:8888"
echo "   arcadedb : http://localhost:2480"
echo "   redis    : localhost:6379"
echo
echo ">> Stop with: ./stop-dockers.sh"
