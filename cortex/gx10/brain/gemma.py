# Gemma 2B service — text-mode rewrite suggestions.
# PRD §6.1 + §8.2.
# Loads on startup so /health reports gemma_loaded=true; real text rewrite
# generation lands when text suggestions are wired into /apply-suggestion.
# See docs/PRD.md §6.1.

from __future__ import annotations
import logging
import os
import uuid
from typing import Any

from . import config

logger = logging.getLogger(__name__)


_INFORMAL_PATTERNS = (
    "kinda", "sorta", "like, ", "like,", "just kinda", "tbh", "lol", "lmao",
    "i didn't really", "i didn", "i kind", "my brain", "felt like",
)


def _scrub_rationale(text: str) -> str:
    """Reject Gemma outputs that drift into first-person/informal voice or that
    are too vague to be specific feedback. Returns "" on rejection so the caller
    falls back to the deterministic template."""
    t = (text or "").strip().strip('"').strip()
    if not t:
        return ""
    low = t.lower()
    if low.startswith(("i ", "i'm", "im ", "my ", "me ", "we ", "you ", "u ")):
        return ""
    for bad in _INFORMAL_PATTERNS:
        if bad in low:
            return ""
    # Keep first sentence only — Gemma 2B drifts into rambling otherwise.
    for term in (". ", "! ", "? "):
        if term in t:
            t = t.split(term)[0].rstrip(".!? ") + "."
            break
    # Reject too-short / generic platitudes that don't reference the segment.
    if len(t) < 25:
        return ""
    generic = ("the segment", "this section", "this part", "this clip", "the clip")
    low2 = t.lower()
    if all(g not in low2 for g in ("\"", "'")) and any(low2.startswith(g) for g in generic):
        # Has no quoted phrase AND opens with a generic pointer — vague.
        return ""
    return t


def _words_in_zone(transcript: list[dict[str, Any]], start: float, end: float) -> str:
    if not transcript:
        return ""
    return " ".join(
        str(w.get("text", "")).strip()
        for w in transcript
        if isinstance(w, dict)
        and float(w.get("start", -1)) >= start - 0.5
        and float(w.get("start", -1)) <= end + 0.5
        and str(w.get("text", "")).strip()
    )


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

    def _generate(self, prompt: str, max_new_tokens: int = 90) -> str:
        if not self._loaded or self._model is None or self._tokenizer is None:
            return ""
        try:
            import torch  # type: ignore

            inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)
            with torch.inference_mode():
                out = self._model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=True,
                    temperature=0.7,
                    top_p=0.9,
                    pad_token_id=self._tokenizer.eos_token_id,
                )
            text = self._tokenizer.decode(
                out[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True
            ).strip()
            # Strip trailing partial sentences.
            for term in ("\n\n", "\n"):
                if term in text:
                    text = text.split(term)[0].strip()
            return text
        except Exception as exc:
            logger.warning("Gemma generation failed: %s", exc)
            return ""

    def video_feedback(
        self,
        transcript: list[dict[str, Any]],
        cold_zones: list[dict[str, Any]],
        engagement_curves: dict[str, list[float]],
    ) -> list[dict[str, Any]]:
        """Per-cold-zone rationale that quotes the actual phrase and names a
        concrete edit. Returns EditSuggestion-shaped dicts (id, cold_zone,
        rationale). Falls back to a templated rationale on Gemma failure.
        """
        suggestions: list[dict[str, Any]] = []
        for zone in cold_zones[:5]:
            start = float(zone.get("start", 0.0))
            end = float(zone.get("end", start))
            quote = _words_in_zone(transcript, start, end)
            quote_clip = quote[:160] + ("…" if len(quote) > 160 else "")
            rationale = ""
            if self._loaded and self._model is not None and quote_clip:
                # Few-shot prompt — Gemma 2B follows demonstrations far more
                # reliably than rule lists. Each shot models the voice + the
                # required structure (quote → diagnosis → fix).
                prompt = (
                    "You are an editorial coach for short-form video. For each "
                    "low-engagement segment, write ONE sentence (≤30 words) "
                    "with this exact structure:\n"
                    "\"<quote fragment>\" <diagnosis>; <concrete fix>.\n\n"
                    "Examples:\n"
                    "Segment: 3.0s–6.0s\n"
                    "Transcript: \"so basically the thing about quantum is\"\n"
                    "Feedback: \"so basically the thing about\" delays the payload "
                    "and loses the viewer; cut the preamble and open on the noun.\n\n"
                    "Segment: 12.0s–15.0s\n"
                    "Transcript: \"it has applications in many fields\"\n"
                    "Feedback: \"applications in many fields\" is too abstract to "
                    "hold attention; replace with a single concrete example shot.\n\n"
                    f"Segment: {start:.1f}s–{end:.1f}s\n"
                    f"Transcript: \"{quote_clip}\"\n"
                    "Feedback:"
                )
                rationale = self._generate(prompt, max_new_tokens=70)
                rationale = _scrub_rationale(rationale)
            if not rationale:
                if quote_clip:
                    short = quote_clip if len(quote_clip) <= 60 else quote_clip[:57] + "…"
                    rationale = (
                        f'"{short}" reads as filler and loses momentum; '
                        "tighten the wording or cut to a concrete visual."
                    )
                else:
                    rationale = (
                        f"Silence from {start:.0f}s to {end:.0f}s breaks pacing; "
                        "trim the gap or layer in a B-roll beat."
                    )
            suggestions.append({
                "id": uuid.uuid4().hex[:8],
                "cold_zone": zone,
                "rationale": rationale,
            })
        return suggestions


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
