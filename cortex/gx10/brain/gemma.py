# Gemma 2B service — text-mode rewrite suggestions.
# PRD §6.1 + §8.2.
# Loads on startup so /health reports gemma_loaded=true; real text rewrite
# generation lands when text suggestions are wired into /apply-suggestion.
# See docs/PRD.md §6.1.

from __future__ import annotations
import logging
import os
from typing import Any

from . import config

logger = logging.getLogger(__name__)


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


gemma_service = GemmaService()
