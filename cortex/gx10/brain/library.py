# Per-creator library + brain/transcript similarity ranking.
# PRD §11.6 + .claude/skills/originality-search/SKILL.md.
# Stacked-matrix numpy cosine — no FAISS, no vector DB. <50ms for ≤10k entries.
# Persistence: cache/library/<creator_id>/<video_id>.json (numpy arrays as nested lists).
# See docs/PRD.md §11.6.

from __future__ import annotations
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from . import config
from .pooling import POOLED_DIM
from .text_embed import EMBED_DIM

logger = logging.getLogger(__name__)


_ROI_NAMES: tuple[str, str, str] = ("visual", "auditory", "language")
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_:.-]{1,128}$")


@dataclass
class LibraryEntry:
    video_id: str
    uploaded_at: str
    duration_s: float
    tribe_pooled: np.ndarray
    roi_means: np.ndarray
    transcript: str
    text_embedding: np.ndarray
    thumbnail_url: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "uploaded_at": self.uploaded_at,
            "duration_s": float(self.duration_s),
            "tribe_pooled": self.tribe_pooled.astype(np.float32).tolist(),
            "roi_means": self.roi_means.astype(np.float32).tolist(),
            "transcript": self.transcript,
            "text_embedding": self.text_embedding.astype(np.float32).tolist(),
            "thumbnail_url": self.thumbnail_url,
        }

    @classmethod
    def from_json(cls, blob: dict[str, Any]) -> "LibraryEntry":
        return cls(
            video_id=str(blob["video_id"]),
            uploaded_at=str(blob["uploaded_at"]),
            duration_s=float(blob["duration_s"]),
            tribe_pooled=np.asarray(blob["tribe_pooled"], dtype=np.float32),
            roi_means=np.asarray(blob["roi_means"], dtype=np.float32),
            transcript=str(blob.get("transcript") or ""),
            text_embedding=np.asarray(blob["text_embedding"], dtype=np.float32),
            thumbnail_url=blob.get("thumbnail_url"),
        )


@dataclass
class LibraryRegistry:
    """In-memory creator_id → list[LibraryEntry], lazy-loaded from disk."""
    root: Path
    _libraries: dict[str, list[LibraryEntry]] = field(default_factory=dict)

    def _creator_dir(self, creator_id: str) -> Path:
        if not _VIDEO_ID_RE.match(creator_id):
            raise ValueError(f"creator_id contains invalid characters: {creator_id!r}")
        return self.root / creator_id

    def load_creator_library(self, creator_id: str) -> list[LibraryEntry]:
        if creator_id in self._libraries:
            return self._libraries[creator_id]
        d = self._creator_dir(creator_id)
        entries: list[LibraryEntry] = []
        if d.exists():
            for p in sorted(d.glob("*.json")):
                try:
                    entries.append(LibraryEntry.from_json(json.loads(p.read_text(encoding="utf-8"))))
                except Exception as exc:
                    logger.error("library entry load failed for %s: %s", p, exc)
        self._libraries[creator_id] = entries
        return entries

    def save_entry(self, creator_id: str, entry: LibraryEntry) -> None:
        if not _VIDEO_ID_RE.match(entry.video_id):
            raise ValueError(f"video_id contains invalid characters: {entry.video_id!r}")
        d = self._creator_dir(creator_id)
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{entry.video_id}.json"
        path.write_text(json.dumps(entry.to_json()), encoding="utf-8")
        lib = self.load_creator_library(creator_id)
        # Replace if same video_id already cached, else append.
        for i, existing in enumerate(lib):
            if existing.video_id == entry.video_id:
                lib[i] = entry
                return
        lib.append(entry)

    def size(self, creator_id: str) -> int:
        return len(self.load_creator_library(creator_id))

    def reset(self) -> None:
        """Test hook — clear in-memory cache (filesystem untouched)."""
        self._libraries.clear()


def _l2(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def per_roi_similarity(draft_roi_means: np.ndarray, lib_roi_means: np.ndarray) -> dict[str, float]:
    """Cosine of single-3-vec ROI means with eps to avoid div0 — values in [-1, 1]."""
    denom = (np.linalg.norm(draft_roi_means) * np.linalg.norm(lib_roi_means)) + 1e-8
    sims = (draft_roi_means * lib_roi_means) / denom
    return {name: float(sims[i]) for i, name in enumerate(_ROI_NAMES)}


def rank_similar(
    draft_brain: np.ndarray,
    draft_text: np.ndarray,
    draft_roi_means: np.ndarray,
    library: list[LibraryEntry],
    top_k: int = config.SIMILARITY_TOP_K,
    alpha: float = config.SIMILARITY_BRAIN_WEIGHT,
) -> list[dict[str, Any]]:
    """Return top-K matches with score + per-ROI breakdown.

    Cold-start gate: returns [] if library < SIMILARITY_MIN_LIBRARY_SIZE.
    Pure function — no side effects, no state.
    """
    if len(library) < config.SIMILARITY_MIN_LIBRARY_SIZE:
        return []
    if draft_brain.shape != (POOLED_DIM,):
        raise ValueError(f"draft_brain must be ({POOLED_DIM},), got {draft_brain.shape}")
    if draft_text.shape != (EMBED_DIM,):
        raise ValueError(f"draft_text must be ({EMBED_DIM},), got {draft_text.shape}")
    if draft_roi_means.shape != (3,):
        raise ValueError(f"draft_roi_means must be (3,), got {draft_roi_means.shape}")

    db = _l2(draft_brain.astype(np.float32))
    dt = _l2(draft_text.astype(np.float32))

    B = np.stack([_l2(e.tribe_pooled.astype(np.float32)) for e in library])
    T = np.stack([_l2(e.text_embedding.astype(np.float32)) for e in library])

    brain_sim = B @ db
    text_sim = T @ dt
    score = alpha * brain_sim + (1.0 - alpha) * text_sim

    k = min(top_k, len(library))
    top_idx = np.argsort(-score)[:k]
    out: list[dict[str, Any]] = []
    for i in top_idx:
        entry = library[int(i)]
        roi_breakdown = per_roi_similarity(draft_roi_means, entry.roi_means)
        dominant = max(roi_breakdown, key=lambda k: roi_breakdown[k])
        out.append({
            "video_id": entry.video_id,
            "score": float(score[i]),
            "thumbnail_url": entry.thumbnail_url,
            "uploaded_at": entry.uploaded_at,
            "duration_s": float(entry.duration_s),
            "dominant_roi": dominant,
            "roi_breakdown": roi_breakdown,
            "text_similarity": float(text_sim[i]),
        })
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


library_registry = LibraryRegistry(root=config.CACHE_DIR / "library")
