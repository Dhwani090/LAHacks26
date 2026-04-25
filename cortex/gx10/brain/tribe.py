# TRIBE inference wrapper — loaded once at startup, called per request.
# PRD §8.1 — see .claude/skills/tribe-inference/SKILL.md for canonical patterns.
# P0-A skeleton: loader + stub predict() that returns synthetic frames.
# Real cortexlab.inference.predictor.TribeModel wiring lands in P1-01.
# See docs/PRD.md §6 + skills/tribe-inference/SKILL.md.

from __future__ import annotations
import logging
import math
import os
from pathlib import Path
from typing import Any

from . import config

logger = logging.getLogger(__name__)


class TribeService:
    def __init__(self) -> None:
        self._model: Any | None = None
        self._loaded = False

    def load(self) -> None:
        """Load TRIBE v2 + LLaMA + Wav2Vec + V-JEPA. Idempotent."""
        if self._loaded:
            return
        if os.environ.get("CORTEX_STUB_TRIBE") == "1":
            logger.warning("CORTEX_STUB_TRIBE=1 — skipping real TRIBE load")
            self._loaded = True
            return
        try:
            # Import lazily so the FastAPI module imports even without cortexlab installed.
            from cortexlab.inference.predictor import TribeModel  # type: ignore
            self._model = TribeModel.from_pretrained(config.TRIBE_MODEL_ID, device="auto")
            self._loaded = True
            logger.info("TRIBE loaded (%s)", config.TRIBE_MODEL_ID)
        except Exception as exc:
            logger.error("TRIBE load failed: %s", exc)
            self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    def analyze_text(self, text: str) -> dict[str, Any]:
        """Stub: returns synthetic 30-frame analysis. Replaced in P1-01."""
        return self._stub_result(mode="text", duration_s=30, has_visual=False, has_audio=False)

    def analyze_audio(self, path: Path) -> dict[str, Any]:
        return self._stub_result(mode="audio", duration_s=30, has_visual=False, has_audio=True)

    def analyze_video(self, path: Path) -> dict[str, Any]:
        return self._stub_result(mode="video", duration_s=30, has_visual=True, has_audio=True)

    @staticmethod
    def _stub_result(mode: str, duration_s: int, has_visual: bool, has_audio: bool) -> dict[str, Any]:
        n = int(duration_s)
        frames = []
        for t in range(n):
            base = math.sin(t * 0.4) * 0.6
            activation = [base + math.sin((v + t) * 0.013) * 0.5 for v in range(config.TRIBE_VERTEX_COUNT)]
            frames.append({"t": float(t), "activation": activation})
        engagement = {
            "language": [math.sin(t * 0.3) * 0.6 + 0.2 for t in range(n)],
        }
        if has_audio:
            engagement["auditory"] = [math.cos(t * 0.25) * 0.4 + 0.1 for t in range(n)]
        if has_visual:
            engagement["visual"] = [math.sin(t * 0.2 + 1) * 0.7 for t in range(n)]
        return {
            "mode": mode,
            "duration_s": duration_s,
            "brain_frames": frames,
            "engagement_curves": engagement,
            "cold_zones": [{"start": 12.0, "end": 16.0, "region": "language", "depth": -0.9}],
        }


tribe_service = TribeService()
