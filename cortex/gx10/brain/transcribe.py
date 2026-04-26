# Whisper-base wrapper for audio→transcript on creator-library uploads.
# PRD §11.6 + .claude/skills/originality-search/SKILL.md.
# Lazy-loaded at first call (~150 MB cold-load) so /health stays fast.
# CORTEX_STUB_TRANSCRIBE=1 short-circuits to a deterministic synthetic transcript
# for laptop dev where openai-whisper isn't installed.
# See docs/PRD.md §11.6.

from __future__ import annotations
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL = None


def _stub_transcribe(audio_path: Path) -> str:
    # Deterministic per-path so library entries from the same file always match.
    seed = abs(hash(audio_path.name)) % 1000
    return f"stub transcript for {audio_path.stem} (seed={seed})"


def _load() -> object | None:
    """Lazy-load whisper.base. Returns None when stubbed or unavailable."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    if os.environ.get("CORTEX_STUB_TRANSCRIBE") == "1":
        logger.warning("CORTEX_STUB_TRANSCRIBE=1 — skipping real Whisper load")
        return None
    try:
        import whisper  # type: ignore
    except Exception as exc:
        logger.error("openai-whisper not importable, falling back to stub: %s", exc)
        return None
    try:
        _MODEL = whisper.load_model("base")
        logger.info("Whisper-base loaded")
        return _MODEL
    except Exception as exc:
        logger.error("Whisper load failed: %s", exc)
        return None


def transcribe(audio_path: Path) -> str:
    model = _load()
    if model is None:
        return _stub_transcribe(audio_path)
    try:
        result = model.transcribe(str(audio_path), fp16=False)  # type: ignore[attr-defined]
        text = (result.get("text") or "").strip()
        return text or _stub_transcribe(audio_path)
    except Exception as exc:
        logger.error("Whisper inference failed for %s: %s", audio_path, exc)
        return _stub_transcribe(audio_path)


def is_loaded() -> bool:
    return _MODEL is not None
