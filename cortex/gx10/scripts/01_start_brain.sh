#!/usr/bin/env bash
# Boot the Cortex backend. Activates conda env, exports HF token, runs uvicorn.
# PRD §3 (backend) + CLAUDE.md §5 (commands).
# Set CORTEX_STUB_TRIBE=1 / CORTEX_STUB_GEMMA=1 to skip model loads (laptop dev).
# Verify with `bash scripts/99_healthcheck.sh`.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${HF_TOKEN:-}" ]]; then
  echo "warn: HF_TOKEN not set — gated model downloads will fail" >&2
fi
export HF_HUB_DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-300}"

# Activate conda env if available
if command -v conda >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate cortex || echo "warn: conda env 'cortex' missing"
fi

exec uvicorn brain.main:app \
  --host "${CORTEX_HOST:-0.0.0.0}" \
  --port "${CORTEX_PORT:-8080}" \
  --workers 1 \
  --log-level info
