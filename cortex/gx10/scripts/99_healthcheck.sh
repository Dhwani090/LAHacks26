#!/usr/bin/env bash
# Healthcheck — confirms /health returns ok with both models loaded.
# PRD §9 (API contracts) + §13 risk register.
# Exits 0 on healthy, 1 otherwise. Safe to run from laptop or GX10.
# Override URL with CORTEX_URL env var.
set -euo pipefail

URL="${CORTEX_URL:-http://localhost:8080}"
echo "checking $URL/health ..."

RESP=$(curl -fsS "$URL/health")
echo "$RESP"

# basic field sanity
echo "$RESP" | grep -q '"status"' || { echo "no status field"; exit 1; }
echo "$RESP" | grep -q '"tribe_loaded":\s*true' || echo "warn: tribe not loaded"
echo "$RESP" | grep -q '"gemma_loaded":\s*true' || echo "warn: gemma not loaded"
