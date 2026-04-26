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

# 2b. neuralset video extractor — bf16 vjepa2 ----------------------------
# vjepa2-vitg is the dominant cost in video analysis (~6.5s/chunk fp32 on Blackwell).
# bf16 weights + bf16 pixel_values → 2-3x throughput on tensor cores.
NEURALSET_VIDEO="$ENV/lib/python3.11/site-packages/neuralset/extractors/video.py"
if [[ ! -f "$NEURALSET_VIDEO" ]]; then
  echo "ERROR: $NEURALSET_VIDEO not found — is neuralset installed?" >&2
  exit 1
fi
if grep -q "PATCHED for cortex/LAHacks26 vjepa2-bf16" "$NEURALSET_VIDEO"; then
  echo "[setup] neuralset video.py already bf16-patched"
else
  echo "[setup] patching neuralset video.py for bf16 vjepa2"
  "$ENV/bin/python" - "$NEURALSET_VIDEO" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1])
src = p.read_text()
old1 = '        if "vjepa2" in model_name:\n            from transformers import AutoVideoProcessor as Processor\n\n        self.model = Model.from_pretrained(model_name, output_hidden_states=True, **extra)'
new1 = (
    '        if "vjepa2" in model_name:\n'
    '            from transformers import AutoVideoProcessor as Processor\n'
    '            # PATCHED for cortex/LAHacks26 vjepa2-bf16: vjepa2-vitg is ~1.8B params; fp32\n'
    '            # encoding is the dominant cost (~6.5s/chunk on Blackwell). bf16 weights with\n'
    '            # bf16 pixel_values give 2-3x throughput on tensor cores with no measurable\n'
    '            # quality drop (per HF model card + LearnOpenCV real-time guide).\n'
    '            extra["torch_dtype"] = torch.bfloat16\n\n'
    '        self.model = Model.from_pretrained(model_name, output_hidden_states=True, **extra)'
)
old2 = '        kwargs[field] = list(images)\n        inputs = self.processor(**kwargs)\n        # prevent nans (happening for uniform images)\n        _fix_pixel_values(inputs)\n        inputs = inputs.to(self.model.device)\n        with torch.inference_mode():\n            pred = self.model(**inputs)\n        return pred'
new2 = (
    '        kwargs[field] = list(images)\n'
    '        inputs = self.processor(**kwargs)\n'
    '        # prevent nans (happening for uniform images)\n'
    '        _fix_pixel_values(inputs)\n'
    '        inputs = inputs.to(self.model.device)\n'
    '        # PATCHED for cortex/LAHacks26 vjepa2-bf16: processor returns fp32 pixel_values;\n'
    '        # cast to model dtype so tensor cores actually engage.\n'
    '        target_dtype = next(self.model.parameters()).dtype\n'
    '        if target_dtype != torch.float32:\n'
    '            for k in ("pixel_values_videos", "pixel_values"):\n'
    '                if k in inputs and inputs[k].dtype.is_floating_point and inputs[k].dtype != target_dtype:\n'
    '                    inputs[k] = inputs[k].to(target_dtype)\n'
    '        with torch.inference_mode():\n'
    '            pred = self.model(**inputs)\n'
    '        return pred'
)
for old, new in ((old1, new1), (old2, new2)):
    if old not in src:
        sys.exit(f"ERROR: expected pattern not found in video.py — neuralset version may have changed:\n{old[:80]}")
    src = src.replace(old, new)
p.write_text(src)
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
