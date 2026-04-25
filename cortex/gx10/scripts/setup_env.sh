#!/usr/bin/env bash
# setup_env.sh — one-shot bootstrap for the cortex conda env on a fresh GX10.
# PH-B per docs/TASKS.md. Skill: .claude/skills/tribe-inference/SKILL.md.
# Idempotent-ish: re-running is safe but skips nothing — meant for first install.
# Requires: HF_TOKEN env var set BEFORE running.
set -euo pipefail

ENV_NAME="${CORTEX_ENV:-cortex}"

if [ -z "${HF_TOKEN:-}" ]; then
  echo "ERROR: export HF_TOKEN=<your_hf_token> before running this script" >&2
  exit 1
fi

source "$(conda info --base)/etc/profile.d/conda.sh"

echo "[1/6] creating conda env $ENV_NAME (python 3.11) ..."
conda create -n "$ENV_NAME" python=3.11 -y

conda activate "$ENV_NAME"

echo "[2/6] persisting HF_HUB_DOWNLOAD_TIMEOUT=300 in ~/.bashrc ..."
grep -q HF_HUB_DOWNLOAD_TIMEOUT ~/.bashrc || echo 'export HF_HUB_DOWNLOAD_TIMEOUT=300' >> ~/.bashrc
export HF_HUB_DOWNLOAD_TIMEOUT=300

echo "[3/6] pinning numpy<2.1 BEFORE tribev2 (ABI guard, see SKILL.md) ..."
pip install --quiet "numpy<2.1" huggingface_hub

echo "[4/6] huggingface login ..."
hf auth login --token "$HF_TOKEN"

echo "[5/6] installing tribev2 + backend deps ..."
pip install "tribev2[plotting] @ git+https://github.com/facebookresearch/tribev2.git"
# `lightning` is an undeclared transitive dep of cortexlab.training — install explicitly.
pip install cortexlab-toolkit transformers ffmpeg-python fastapi uvicorn sse-starlette pydantic accelerate lightning

echo "[6/6] pre-downloading model weights (LLaMA, Gemma, TRIBE) ..."
python - <<'PY'
from huggingface_hub import snapshot_download
for repo in ["meta-llama/Llama-3.2-3B", "google/gemma-2-2b-it", "facebook/tribev2"]:
    print(f"downloading {repo} ...")
    snapshot_download(repo)
PY

echo ""
echo "✅ env $ENV_NAME ready. Activate with:  conda activate $ENV_NAME"
echo "   verify with: python -c \"from cortexlab.inference.predictor import TribeModel; m = TribeModel.from_pretrained('facebook/tribev2', device='auto'); print('LOADED')\""
