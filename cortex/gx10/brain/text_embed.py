# nomic-embed-text-v1.5 wrapper for transcript→768-dim L2-normed vector.
# PRD §11.6 + .claude/skills/originality-search/SKILL.md.
# Lazy-loaded (~550 MB) at first call.
# CORTEX_STUB_EMBED=1 → deterministic hashed pseudo-vector for laptop dev.
# See docs/PRD.md §11.6.

from __future__ import annotations
import hashlib
import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

EMBED_DIM = 768

_MODEL = None


def _stub_embed(text: str) -> np.ndarray:
    """Deterministic 768-dim L2-normed vector seeded from sha256(text).
    Same text always gets the same vector; different texts get different vectors,
    so library cosine-similarity ranking exercises the right code paths under stub."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "big") & 0xFFFFFFFF
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(EMBED_DIM).astype(np.float32)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def _load() -> object | None:
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    if os.environ.get("CORTEX_STUB_EMBED") == "1":
        logger.warning("CORTEX_STUB_EMBED=1 — skipping real nomic-embed load")
        return None
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as exc:
        logger.error("sentence-transformers not importable, falling back to stub: %s", exc)
        return None
    try:
        _MODEL = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)
        logger.info("nomic-embed-text-v1.5 loaded")
        return _MODEL
    except Exception as exc:
        logger.error("nomic-embed load failed: %s", exc)
        return None


def embed_text(text: str) -> np.ndarray:
    """Return a 768-dim L2-normalized float32 vector. Empty string → zero vector."""
    if not text or not text.strip():
        return np.zeros(EMBED_DIM, dtype=np.float32)
    model = _load()
    if model is None:
        return _stub_embed(text)
    try:
        v = model.encode(text, normalize_embeddings=True)  # type: ignore[attr-defined]
        arr = np.asarray(v, dtype=np.float32).reshape(-1)
        if arr.shape[0] != EMBED_DIM:
            logger.error("nomic returned dim=%d, expected %d — stubbing", arr.shape[0], EMBED_DIM)
            return _stub_embed(text)
        return arr
    except Exception as exc:
        logger.error("nomic-embed inference failed: %s", exc)
        return _stub_embed(text)


def is_loaded() -> bool:
    return _MODEL is not None
