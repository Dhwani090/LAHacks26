# TRIBE inference wrapper — loaded once at startup, called per request.
# PRD §8.1 — see .claude/skills/tribe-inference/SKILL.md for canonical patterns.
# Real TribeModel calls per modality (P1-01); stubs removed.
# CORTEX_STUB_TRIBE=1 still skips the load for laptop dev — analyze_* will then refuse.
# See docs/PRD.md §6 + skills/tribe-inference/SKILL.md.

from __future__ import annotations
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

from . import config
from .pooling import ROI_GROUPS, get_roi_indices

logger = logging.getLogger(__name__)

# TRIBE's published minimum useful input is ~15s of content (skill: tribe-inference
# §"What TRIBE CANNOT do"). For text-mode TTS, ~12 words is the floor at average pacing.
MIN_TEXT_WORDS = 12

_WARMUP_TEXT = (
    "The quick brown fox jumps over the lazy dog. "
    "She sells seashells by the seashore. "
    "Peter picked a peck of pickled peppers."
)


class TooShortInputError(ValueError):
    """Raised when input is below TRIBE's minimum useful length. Mapped to HTTP 400."""


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
            from cortexlab.inference.predictor import TribeModel  # type: ignore
            # data.frequency=1.0 halves inference time vs the checkpoint default
            # of 2Hz and aligns model output with config.TRIBE_FRAME_RATE_HZ.
            self._model = TribeModel.from_pretrained(
                config.TRIBE_MODEL_ID,
                device="auto",
                config_update={"data.frequency": 1.0},
            )
            self._loaded = True
            logger.info("TRIBE loaded (%s)", config.TRIBE_MODEL_ID)
        except Exception as exc:
            logger.error("TRIBE load failed: %s", exc)
            self._loaded = False
            return
        self._warm_up()

    @property
    def loaded(self) -> bool:
        return self._loaded

    def analyze_text(self, text: str) -> dict[str, Any]:
        word_count = len(text.split())
        if word_count < MIN_TEXT_WORDS:
            raise TooShortInputError(
                f"text must be ≥ {MIN_TEXT_WORDS} words for TRIBE (got {word_count})"
            )
        self._require_real_model()
        # Skill §gotcha #4: write → flush → fsync → close before passing path to TRIBE.
        # tempfile.NamedTemporaryFile closes on context exit, so the read happens after fsync.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
            tmp_path = f.name
        try:
            preds, transcript = self._run(text_path=tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return self._build_result(preds, transcript, mode="text", has_audio=False, has_visual=False)

    def analyze_audio(self, path: Path) -> dict[str, Any]:
        self._require_real_model()
        preds, transcript = self._run(audio_path=str(path))
        return self._build_result(preds, transcript, mode="audio", has_audio=True, has_visual=False)

    def analyze_video(self, path: Path) -> dict[str, Any]:
        self._require_real_model()
        preds, transcript = self._run(video_path=str(path))
        return self._build_result(preds, transcript, mode="video", has_audio=True, has_visual=True)

    def _require_real_model(self) -> None:
        if os.environ.get("CORTEX_STUB_TRIBE") == "1" or self._model is None:
            raise RuntimeError(
                "TRIBE model is not loaded — refusing to return synthetic data. "
                "Unset CORTEX_STUB_TRIBE and verify load() succeeded."
            )

    def _run(
        self,
        text_path: str | None = None,
        audio_path: str | None = None,
        video_path: str | None = None,
    ) -> tuple[np.ndarray, list[dict[str, Any]]]:
        df = self._model.get_events_dataframe(
            text_path=text_path, audio_path=audio_path, video_path=video_path
        )
        preds, _segments = self._model.predict(events=df, verbose=False)
        preds = np.asarray(preds, dtype=np.float32)
        if preds.ndim != 2 or preds.shape[1] != config.TRIBE_VERTEX_COUNT:
            raise RuntimeError(
                f"TRIBE returned unexpected shape {preds.shape}, "
                f"expected (T, {config.TRIBE_VERTEX_COUNT})"
            )
        if preds.shape[0] < 2:
            raise RuntimeError(f"TRIBE returned T={preds.shape[0]} timesteps; need ≥ 2")
        return preds, self._extract_transcript(df)

    @staticmethod
    def _extract_transcript(df: Any) -> list[dict[str, Any]]:
        """Pull word-level timing out of the events df. Returns [] if absent.

        Frontend tolerates an empty list (streaming.transcript event still fires).
        """
        if df is None or len(df) == 0:
            return []
        cols = set(getattr(df, "columns", []))
        if "text" not in cols or "start" not in cols:
            return []
        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            txt = row["text"]
            if not isinstance(txt, str) or not txt.strip():
                continue
            try:
                start = float(row["start"])
            except (TypeError, ValueError):
                continue
            if "end" in cols:
                try:
                    end = float(row["end"])
                except (TypeError, ValueError):
                    end = start
            elif "duration" in cols:
                try:
                    end = start + float(row["duration"])
                except (TypeError, ValueError):
                    end = start
            else:
                end = start
            out.append({"text": txt.strip(), "start": start, "end": end})
        return out

    def _build_result(
        self,
        preds: np.ndarray,
        transcript: list[dict[str, Any]],
        mode: str,
        has_audio: bool,
        has_visual: bool,
    ) -> dict[str, Any]:
        T = preds.shape[0]
        roi = get_roi_indices()

        def curve_for(group: str) -> np.ndarray:
            regions = ROI_GROUPS[group]
            parts = [roi[r] for r in regions if r in roi]
            if not parts:
                idx = np.arange(config.TRIBE_VERTEX_COUNT, dtype=np.int64)
            else:
                idx = np.concatenate(parts)
            return preds[:, idx].mean(axis=1).astype(np.float32)

        engagement: dict[str, list[float]] = {}
        language_curve = curve_for("language")
        engagement["language"] = language_curve.tolist()
        if has_audio:
            engagement["auditory"] = curve_for("auditory").tolist()
        if has_visual:
            engagement["visual"] = curve_for("visual").tolist()

        # Cold zones detected on the language curve — most stable signal across modes.
        cold_zones = self._cold_zones(language_curve)

        brain_frames = [
            {"t": float(t), "activation": preds[t].tolist()} for t in range(T)
        ]
        result: dict[str, Any] = {
            "mode": mode,
            "duration_s": float(T),
            "brain_frames": brain_frames,
            "engagement_curves": engagement,
            "cold_zones": cold_zones,
        }
        if has_audio or has_visual:
            result["transcript"] = transcript
        return result

    @staticmethod
    def _cold_zones(curve: np.ndarray) -> list[dict[str, Any]]:
        """Runs where the language curve sits in its bottom quartile.

        The absolute z-threshold (`COLD_THRESHOLD_Z`) was too strict in practice —
        TRIBE's per-clip variance is small (~0.05 std) so an absolute cut never
        triggered. Using the clip's own 25th percentile guarantees we surface the
        weakest moments of *this* clip, which is what a creator actually wants.
        """
        T = len(curve)
        if T == 0:
            return []
        sample_period = 1.0 / config.TRIBE_FRAME_RATE_HZ
        threshold = float(np.percentile(curve, 25))
        absolute_floor = float(config.COLD_THRESHOLD_Z)
        cutoff = max(threshold, absolute_floor) if threshold < 0 else threshold
        below = curve < cutoff
        out: list[dict[str, Any]] = []
        i = 0
        # Slightly relaxed minimum — at 1Hz, 2 consecutive frames is a real dip.
        min_frames = max(2, int(round(config.COLD_MIN_DURATION_S * config.TRIBE_FRAME_RATE_HZ)))
        while i < T:
            if not below[i]:
                i += 1
                continue
            j = i
            while j < T and below[j]:
                j += 1
            if (j - i) >= min_frames:
                out.append({
                    "start": float(i * sample_period),
                    "end": float(j * sample_period),
                    "region": "language",
                    "depth": float(curve[i:j].min()),
                })
            i = j
        return out

    def _warm_up(self) -> None:
        """One throwaway text inference so the first real request hits a hot path."""
        if self._model is None:
            return
        t0 = time.perf_counter()
        try:
            self.analyze_text(_WARMUP_TEXT)
            logger.info("TRIBE warmup complete in %.1fs", time.perf_counter() - t0)
        except Exception as exc:
            # Warmup is best-effort — don't block startup if it fails.
            logger.warning("TRIBE warmup failed (non-fatal): %s", exc)


tribe_service = TribeService()
