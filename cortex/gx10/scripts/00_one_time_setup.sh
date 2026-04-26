#!/usr/bin/env bash
# One-time GX10 environment fixes for the cortex/brain backend.
# PRD §3 (backend) + CLAUDE.md §5 (commands).
# Run AFTER conda env "cortex" is created and torch nightly cu128 is installed.
# Idempotent — safe to re-run on every fresh machine; no-ops once applied.
#
# Captures three host-side patches that aren't expressible as pip requirements:
#   1) ffmpeg in the cortex conda env (cortexlab whisperx subprocess decodes audio).
#   2) cortexlab/data/transforms.py — force --device cpu for whisperx (uvx env has
#      no CUDA-enabled CTranslate2 wheel for aarch64).
#   3) uvx whisperx archive — remove the broken aarch64 CUDA torchcodec wheel
#      (pyannote-audio drags torchcodec in despite whisperx not needing it on aarch64,
#      and the only aarch64 torchcodec wheels require CUDA torch which uvx doesn't have).
set -euo pipefail

ENV="$HOME/miniforge3/envs/cortex"
UV="$HOME/.local/bin/uv"
CONDA="$HOME/miniforge3/bin/conda"

if [[ ! -d "$ENV" ]]; then
  echo "ERROR: conda env not found at $ENV" >&2
  exit 1
fi

# 1. ffmpeg --------------------------------------------------------------
if [[ ! -x "$ENV/bin/ffmpeg" ]]; then
  echo "[setup] installing ffmpeg into cortex env"
  "$CONDA" install -n cortex -c conda-forge ffmpeg -y
else
  echo "[setup] ffmpeg already present ($("$ENV/bin/ffmpeg" -version | head -1))"
fi

# 2. cortexlab transforms.py patch ---------------------------------------
TRANSFORMS_PY="$ENV/lib/python3.11/site-packages/cortexlab/data/transforms.py"
if [[ ! -f "$TRANSFORMS_PY" ]]; then
  echo "ERROR: $TRANSFORMS_PY not found — is cortexlab-toolkit installed?" >&2
  exit 1
fi
if grep -q "PATCHED for cortex/LAHacks26" "$TRANSFORMS_PY"; then
  echo "[setup] cortexlab transforms.py already patched"
else
  echo "[setup] patching cortexlab transforms.py for CPU whisperx"
  "$ENV/bin/python" - "$TRANSFORMS_PY" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1])
src = p.read_text()
old = '        device = "cuda" if torch.cuda.is_available() else "cpu"\n        compute_type = "float16"'
new = (
    '        # PATCHED for cortex/LAHacks26: uvx whisperx env has CPU-only ctranslate2,\n'
    '        # so passing --device cuda fails. Force CPU regardless of parent torch state.\n'
    '        # Original: device = "cuda" if torch.cuda.is_available() else "cpu"\n'
    '        device = "cpu"\n'
    '        compute_type = "int8"  # float16 is GPU-only in CTranslate2; int8 is the CPU equivalent'
)
if old not in src:
    sys.exit("ERROR: expected pattern not found in transforms.py — cortexlab version may have changed")
p.write_text(src.replace(old, new))
print("[setup]   patched")
PY
fi

# 3. uvx whisperx env: remove broken aarch64 CUDA torchcodec -------------
if [[ ! -x "$UV" ]]; then
  echo "ERROR: uv not found at $UV — install with: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

echo "[setup] populating uvx whisperx archive (first call may install ~100 packages)"
PATH="$ENV/bin:$PATH" "$HOME/.local/bin/uvx" whisperx --version >/dev/null

REMOVED=0
for archive in "$HOME"/.cache/uv/archive-v0/*/; do
  [[ -d "$archive" ]] || continue
  # find the python in this archive (3.11, 3.12, 3.13, ...)
  PY_BIN=$(ls -d "$archive"bin/python* 2>/dev/null | head -1 || true)
  [[ -x "$PY_BIN" ]] || continue
  # only target archives that contain whisperx
  if ls -d "$archive"lib/python*/site-packages/whisperx 2>/dev/null | grep -q .; then
    if ls -d "$archive"lib/python*/site-packages/torchcodec 2>/dev/null | grep -q .; then
      echo "[setup] removing torchcodec from $archive"
      "$UV" pip uninstall --python "$PY_BIN" torchcodec
      REMOVED=$((REMOVED + 1))
    fi
  fi
done
if [[ $REMOVED -eq 0 ]]; then
  echo "[setup] no whisperx archive needed torchcodec removal (already clean)"
fi

echo "[setup] done — run scripts/01_start_brain.sh next"
