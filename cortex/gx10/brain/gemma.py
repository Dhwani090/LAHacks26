# Gemma 2B service — edit suggestions + auto-improve reasoning.
# PRD §8.2 + skills/auto-improve/SKILL.md.
# P0-A skeleton: loader + stub stream_completion that yields canned tokens.
# Real transformers wiring lands in P1-06.
# See docs/PRD.md §8.2.

from __future__ import annotations
import asyncio
import logging
import os
from typing import Any, AsyncIterator

from . import config

logger = logging.getLogger(__name__)

_STUB_TOKENS = [
    "Looking at the engagement curves, ",
    "the language track dips hardest around 0:14 — ",
    "viewers lost the thread mid-sentence. ",
    "Cutting that 7-second filler should restore retention. ",
    '\n\n```json\n{"reasoning":"language drop at 0:14, removing filler","operation":"cut","params":{"start_t":14.0,"end_t":21.0}}\n```',
]


class GemmaService:
    def __init__(self) -> None:
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        if os.environ.get("CORTEX_STUB_GEMMA") == "1":
            logger.warning("CORTEX_STUB_GEMMA=1 — skipping real Gemma load")
            self._loaded = True
            return
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
            self._tokenizer = AutoTokenizer.from_pretrained(config.GEMMA_MODEL_ID)
            self._model = AutoModelForCausalLM.from_pretrained(
                config.GEMMA_MODEL_ID, device_map="auto"
            )
            self._loaded = True
            logger.info("Gemma loaded (%s)", config.GEMMA_MODEL_ID)
        except Exception as exc:
            logger.error("Gemma load failed: %s", exc)
            self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    async def stream_completion(self, system: str, user: str) -> AsyncIterator[str]:
        """Yields generation tokens. Stub returns canned reasoning; real impl in P1-06."""
        if os.environ.get("CORTEX_STUB_GEMMA") == "1" or self._model is None:
            for tok in _STUB_TOKENS:
                await asyncio.sleep(0.18)
                yield tok
            return
        # Real path placeholder — implement in P1-06 with TextIteratorStreamer.
        raise NotImplementedError("real Gemma streaming wired in P1-06")


gemma_service = GemmaService()
