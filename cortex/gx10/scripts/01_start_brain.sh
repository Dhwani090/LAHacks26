#!/usr/bin/env bash
# Boot the Cortex backend on the GX10.
# PRD §3 (backend) + CLAUDE.md §5 (commands).
# Required: HF_TOKEN env var (export in ~/.bashrc), conda env "cortex" (PH-B).
# Optional: CORTEX_STUB_TRIBE=1 / CORTEX_STUB_GEMMA=1 to skip model loads (laptop dev).
# Verify with `bash scripts/99_healthcheck.sh`.
set -euo pipefail

cd "$(dirname "$0")/.."

# `uvx` is required by cortexlab.data.transforms for whisperx-based word alignment
# (every text/audio/video TRIBE call). uv installer puts it in ~/.local/bin which
# isn't on the default non-interactive bash PATH.
export PATH="$HOME/.local/bin:$PATH"

# ---------------------------------------------------------------------------
# 1. HF token + downloads timeout (gated weights: LLaMA-3.2-3B + Gemma-2-2B).
# ---------------------------------------------------------------------------
if [[ -z "${HF_TOKEN:-}" ]]; then
  echo "ERROR: HF_TOKEN is not set." >&2
  echo "  Add to ~/.bashrc:  export HF_TOKEN=hf_xxxxx" >&2
  echo "  Then: source ~/.bashrc" >&2
  exit 1
fi
export HF_HUB_DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-300}"
# huggingface_hub picks up either HF_TOKEN or HUGGING_FACE_HUB_TOKEN.
export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"

# ---------------------------------------------------------------------------
# 2. Conda env activation (cortex env from PH-B).
# ---------------------------------------------------------------------------
if command -v conda >/dev/null 2>&1; then
  CONDA_BASE="$(conda info --base)"
  # shellcheck disable=SC1091
  source "$CONDA_BASE/etc/profile.d/conda.sh"
  if conda env list | grep -q '^cortex\b'; then
    conda activate cortex
    echo "[start_brain] conda env: cortex (python $(python --version 2>&1 | awk '{print $2}'))"
  else
    echo "ERROR: conda env 'cortex' not found." >&2
    echo "  Create it: conda create -n cortex python=3.11 -y" >&2
    echo "  Then run scripts/setup_env.sh (PH-B)." >&2
    exit 1
  fi
else
  echo "warn: conda not found — using system python ($(which python))" >&2
fi

# ---------------------------------------------------------------------------
# 3. Sanity-check required python deps so we fail fast with a useful message
#    instead of crashing inside uvicorn 30s later.
# ---------------------------------------------------------------------------
MISSING=()
for mod in fastapi uvicorn sse_starlette pydantic; do
  if ! python -c "import $mod" 2>/dev/null; then
    MISSING+=("$mod")
  fi
done
if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "ERROR: missing python packages: ${MISSING[*]}" >&2
  echo "  Install: pip install -r requirements.txt" >&2
  exit 1
fi

# Optional deps — warn but don't exit (stub mode lets you run without them).
if ! python -c "import cortexlab" 2>/dev/null; then
  if [[ "${CORTEX_STUB_TRIBE:-}" != "1" ]]; then
    echo "warn: cortexlab not installed — set CORTEX_STUB_TRIBE=1 OR pip install cortexlab-toolkit" >&2
  fi
else
  # Vendor-side patches that aren't expressible as pip requirements (see 00_one_time_setup.sh).
  # Fail fast here so we don't crash 70s into TRIBE warmup on a fresh machine.
  TRANSFORMS_PY="$(python -c 'import cortexlab.data.transforms as m; print(m.__file__)')"
  if ! grep -q "PATCHED for cortex/LAHacks26" "$TRANSFORMS_PY"; then
    echo "ERROR: cortexlab vendor patch missing." >&2
    echo "  Run: bash scripts/00_one_time_setup.sh" >&2
    exit 1
  fi
  NEURALSET_VIDEO_PY="$(python -c 'import neuralset.extractors.video as m; print(m.__file__)')"
  if ! grep -q "PATCHED for cortex/LAHacks26 vjepa2-bf16" "$NEURALSET_VIDEO_PY"; then
    echo "ERROR: neuralset vjepa2-bf16 patch missing." >&2
    echo "  Run: bash scripts/00_one_time_setup.sh" >&2
    exit 1
  fi
fi
if ! python -c "import transformers" 2>/dev/null; then
  if [[ "${CORTEX_STUB_GEMMA:-}" != "1" ]]; then
    echo "warn: transformers not installed — set CORTEX_STUB_GEMMA=1 OR pip install transformers" >&2
  fi
fi
# ---------------------------------------------------------------------------
# 4. Boot uvicorn. Workers=1 so the in-memory _JOBS dict isn't sharded.
# ---------------------------------------------------------------------------
HOST="${CORTEX_HOST:-0.0.0.0}"
PORT="${CORTEX_PORT:-8080}"
echo "[start_brain] launching uvicorn brain.main:app on $HOST:$PORT"
[[ "${CORTEX_STUB_TRIBE:-}" == "1" ]] && echo "[start_brain] CORTEX_STUB_TRIBE=1 — TRIBE inference is stubbed"
[[ "${CORTEX_STUB_GEMMA:-}" == "1" ]] && echo "[start_brain] CORTEX_STUB_GEMMA=1 — Gemma generation is stubbed"

exec uvicorn brain.main:app \
  --host "$HOST" \
  --port "$PORT" \
  --workers 1 \
  --log-level info
