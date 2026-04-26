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

    def generate(self, prompt: str, max_new_tokens: int = 128) -> str:
        """Generate a completion for `prompt`. Returns "" if unloaded so callers
        can fall back without crashing.

        Stub mode (`CORTEX_STUB_GEMMA=1`) returns a deterministic canned response
        derived from the prompt — enough for unit tests that just need *something*
        non-empty back. Real Gemma weights take over once the env var is unset.
        """
        if not self._loaded:
            return ""
        if os.environ.get("CORTEX_STUB_GEMMA") == "1":
            return _stub_response(prompt)
        if self._model is None or self._tokenizer is None:
            return ""
        try:
            inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=config.GEMMA_TEMPERATURE,
                pad_token_id=self._tokenizer.eos_token_id,
            )
            text = self._tokenizer.decode(outputs[0], skip_special_tokens=True)
            # Strip the echoed prompt. transformers usually returns prompt+completion,
            # but some Gemma builds echo only partially or normalize whitespace, which
            # breaks a naive startswith(). Prefer splitting on a sentinel the prompt
            # template ends with ("Search queries:" / "Output:" etc.) and take the
            # suffix; only fall back to startswith() when no sentinel is found.
            for sentinel in ("Search queries:", "Output:", "Answer:"):
                if sentinel in prompt and sentinel in text:
                    text = text.rsplit(sentinel, 1)[-1]
                    break
            else:
                if text.startswith(prompt):
                    text = text[len(prompt):]
            return text.strip()
        except Exception as exc:
            logger.error("Gemma generate failed: %s", exc)
            return ""


def _stub_response(prompt: str) -> str:
    """Deterministic canned response for tests. Recognizes the curator's gap-translator
    prompt and returns 5 newline-separated queries; otherwise echoes a generic line."""
    if "search queries" in prompt.lower() or "yt-dlp" in prompt.lower():
        return (
            "viral cooking shorts hook\n"
            "asmr asmr trending shorts\n"
            "fitness motivation shorts\n"
            "explainer shorts science\n"
            "comedy skit shorts viral"
        )
    return "stub response."


gemma_service = GemmaService()
