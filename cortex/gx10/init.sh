#!/usr/bin/env bash
# init.sh — per-session initializer for Cortex backend work on the GX10.
# Sourced (NOT executed) at the start of each Claude Code / shell session.
# Activates the cortex conda env, exports required envs, prints a status banner.
# Pattern: Anthropic Claude Code harness initializer.

source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate cortex 2>/dev/null || {
  echo "⚠️  cortex env not found. Run scripts/setup_env.sh first." >&2
  return 1 2>/dev/null || exit 1
}

export HF_HUB_DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-300}"
export PYTHONPATH="${PYTHONPATH:-}:$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cat <<EOF
== Cortex GX10 session ==
  env:    $(python -V 2>&1 | head -1) ($(which python))
  numpy:  $(python -c "import numpy; print(numpy.__version__)" 2>/dev/null || echo "NOT INSTALLED")
  HF:     $(hf auth whoami 2>&1 | head -1)
  cwd:    $(pwd)
  log:    cortex/gx10/progress.txt
EOF
