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

    def delete_entry(self, creator_id: str, video_id: str) -> bool:
        """Remove a single library entry from disk + in-memory cache.

        Returns True if the entry existed and was removed, False if not found.
        Validates the video_id against the same regex used at write time so a
        crafted id can't escape the creator's library directory.
        """
        if not _VIDEO_ID_RE.match(video_id):
            raise ValueError(f"video_id contains invalid characters: {video_id!r}")
        d = self._creator_dir(creator_id)
        path = d / f"{video_id}.json"
        existed = path.exists()
        path.unlink(missing_ok=True)
        # Update the in-memory list if it's already loaded.
        if creator_id in self._libraries:
            self._libraries[creator_id] = [
                e for e in self._libraries[creator_id] if e.video_id != video_id
            ]
        return existed

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
    min_library: int = config.SIMILARITY_MIN_LIBRARY_SIZE,
) -> list[dict[str, Any]]:
    """Return top-K matches with score + per-ROI breakdown.

    Cold-start gate: returns [] if `len(library) < min_library`.
    Default `min_library` matches the §11.6 creator-library gate (5);
    R-05 inspiration overrides to 1 so a sparse trending pool still ranks.
    Pure function — no side effects, no state.
    """
    if len(library) < min_library:
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


def _parse_iso(s: str) -> datetime | None:
    """Tolerant ISO-8601 parser. Library entries always carry timezone-aware
    timestamps written by `now_iso`, but if a hand-edited file slips through
    we don't want one bad row to crash the whole rank."""
    try:
        # `fromisoformat` accepts the "+00:00" form Python emits; trailing 'Z'
        # is rejected pre-3.11 and supported on 3.11+, so normalize here too.
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def filter_candidates(
    library: list[LibraryEntry],
    last_n: int | None = 50,
    since_days: int | None = None,
    now: datetime | None = None,
) -> list[LibraryEntry]:
    """Slice the library down to the candidate set the user wants to compare against.

    Order of operations:
      1. Sort by uploaded_at DESC (newest first).
      2. If `since_days` is set, drop entries older than that.
      3. If `last_n` is a positive int, take the first N.

    Returns a new list — never mutates the input. Library entries with
    unparseable `uploaded_at` are kept (rather than silently dropped) when
    no time filter is active, and excluded only when since_days requires it.
    """
    sortable: list[tuple[datetime | None, LibraryEntry]] = [
        (_parse_iso(e.uploaded_at), e) for e in library
    ]
    # Sort: parseable entries newest-first, unparseable at the tail.
    sortable.sort(
        key=lambda t: (t[0] is None, -(t[0].timestamp() if t[0] else 0))
    )

    if since_days is not None:
        cutoff_now = now or datetime.now(timezone.utc)
        cutoff = cutoff_now.timestamp() - since_days * 86400.0
        sortable = [(d, e) for (d, e) in sortable if d is not None and d.timestamp() >= cutoff]

    out = [e for (_d, e) in sortable]
    if last_n is not None and last_n > 0:
        out = out[:last_n]
    return out


library_registry = LibraryRegistry(root=config.CACHE_DIR / "library")


# ---------------------------------------------------------------------------
# R-05 — creator centroid + trending pool (PRD §11.8 inspiration feed).
# ---------------------------------------------------------------------------


def compute_centroid(
    library: list[LibraryEntry],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """L2-normalized mean of (tribe_pooled, text_embedding, roi_means) across
    library entries. Used as the "draft" vectors for inspiration ranking.

    Empty library → ValueError (caller must gate on len(library) ≥ MIN before
    calling). All-zero edge case (degenerate corpus) returns the zero vector
    instead of NaN — `_l2` falls through cleanly.
    """
    if not library:
        raise ValueError("compute_centroid requires at least one library entry")
    brain_mean = np.mean(
        np.stack([e.tribe_pooled.astype(np.float32) for e in library]), axis=0
    )
    text_mean = np.mean(
        np.stack([e.text_embedding.astype(np.float32) for e in library]), axis=0
    )
    roi_mean = np.mean(
        np.stack([e.roi_means.astype(np.float32) for e in library]), axis=0
    )
    return _l2(brain_mean), _l2(text_mean), roi_mean


def load_trending_pool(
    trending_dir: Path,
) -> tuple[list[LibraryEntry], dict[str, dict[str, Any]]]:
    """Walk every cache/trending/<yyyy-mm-dd>/<id>.json, parse into LibraryEntry
    instances, and surface trending-specific extras (`source_url`,
    `creator_handle`, `view_count`, `engagement_rate`) keyed by `video_id`.

    Returns ([], {}) for a missing dir. Entries with a missing or all-zero
    `text_embedding` are skipped — they'd produce noise in the cosine fusion.
    """
    if not trending_dir.exists():
        return [], {}
    entries: list[LibraryEntry] = []
    extras: dict[str, dict[str, Any]] = {}
    for date_dir in sorted(trending_dir.iterdir()):
        if not date_dir.is_dir():
            continue
        for json_path in sorted(date_dir.glob("*.json")):
            try:
                blob = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.error("trending entry parse failed %s: %s", json_path, exc)
                continue
            text_emb = blob.get("text_embedding")
            if not isinstance(text_emb, list) or not text_emb:
                continue
            arr = np.asarray(text_emb, dtype=np.float32)
            if not np.any(arr):
                continue  # all-zero embedding (empty transcript) → noise
            try:
                entry = LibraryEntry.from_json(blob)
            except Exception as exc:
                logger.error("trending entry shape mismatch %s: %s", json_path, exc)
                continue
            # Hard shape gate — mixed dims would crash np.stack inside rank_similar.
            if (
                entry.tribe_pooled.shape != (POOLED_DIM,)
                or entry.text_embedding.shape != (EMBED_DIM,)
                or entry.roi_means.shape != (3,)
            ):
                logger.error("trending entry has wrong vector shapes %s — skipping", json_path)
                continue
            entries.append(entry)
            extras[entry.video_id] = {
                "source_url": blob.get("source_url"),
                "creator_handle": blob.get("creator_handle"),
                "view_count": int(blob.get("view_count") or 0),
                "engagement_rate": float(blob.get("engagement_rate") or 0.0),
            }
    return entries, extras
