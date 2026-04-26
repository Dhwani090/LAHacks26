"""Unit tests for brain.library — LibraryEntry persistence + rank_similar.

PRD §11.6 + .claude/skills/originality-search/SKILL.md.
Pure unit tests — no FastAPI, no real Whisper/nomic; uses synthetic vectors.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("CORTEX_STUB_TRIBE", "1")
os.environ.setdefault("CORTEX_STUB_TRANSCRIBE", "1")
os.environ.setdefault("CORTEX_STUB_EMBED", "1")

from datetime import datetime, timedelta, timezone  # noqa: E402

from brain import config  # noqa: E402
from brain.library import (  # noqa: E402
    LibraryEntry,
    LibraryRegistry,
    filter_candidates,
    now_iso,
    per_roi_similarity,
    rank_similar,
)
from brain.pooling import POOLED_DIM  # noqa: E402
from brain.text_embed import EMBED_DIM  # noqa: E402


def _make_entry(seed: int, video_id: str | None = None) -> LibraryEntry:
    rng = np.random.default_rng(seed)
    pooled = rng.standard_normal(POOLED_DIM).astype(np.float32)
    text_vec = rng.standard_normal(EMBED_DIM).astype(np.float32)
    text_vec /= float(np.linalg.norm(text_vec))
    return LibraryEntry(
        video_id=video_id or f"vid_{seed:03d}",
        uploaded_at=now_iso(),
        duration_s=30.0 + seed % 30,
        tribe_pooled=pooled,
        roi_means=rng.standard_normal(3).astype(np.float32),
        transcript=f"transcript {seed}",
        text_embedding=text_vec,
    )


def test_library_entry_round_trip(tmp_path):
    e = _make_entry(seed=7, video_id="abc123")
    blob = e.to_json()
    restored = LibraryEntry.from_json(blob)
    assert restored.video_id == "abc123"
    assert restored.duration_s == e.duration_s
    np.testing.assert_allclose(restored.tribe_pooled, e.tribe_pooled, atol=1e-6)
    np.testing.assert_allclose(restored.roi_means, e.roi_means, atol=1e-6)
    np.testing.assert_allclose(restored.text_embedding, e.text_embedding, atol=1e-6)


def test_library_registry_save_load_isolation(tmp_path):
    reg = LibraryRegistry(root=tmp_path)
    reg.save_entry("creatorA", _make_entry(1, "v1"))
    reg.save_entry("creatorA", _make_entry(2, "v2"))
    reg.save_entry("creatorB", _make_entry(3, "v1"))

    # Round-trip through a fresh registry to verify on-disk state.
    reg2 = LibraryRegistry(root=tmp_path)
    libA = reg2.load_creator_library("creatorA")
    libB = reg2.load_creator_library("creatorB")
    assert {e.video_id for e in libA} == {"v1", "v2"}
    assert {e.video_id for e in libB} == {"v1"}


def test_library_registry_save_replaces_same_video_id(tmp_path):
    reg = LibraryRegistry(root=tmp_path)
    first = _make_entry(1, "shared")
    second = _make_entry(2, "shared")
    reg.save_entry("creator", first)
    reg.save_entry("creator", second)
    lib = reg.load_creator_library("creator")
    assert len(lib) == 1
    np.testing.assert_allclose(lib[0].tribe_pooled, second.tribe_pooled)


def test_library_registry_rejects_path_traversal(tmp_path):
    reg = LibraryRegistry(root=tmp_path)
    with pytest.raises(ValueError):
        reg.load_creator_library("../escape")
    with pytest.raises(ValueError):
        reg.save_entry("creator", _make_entry(1, "../escape"))


def test_rank_similar_cold_start_returns_empty():
    library = [_make_entry(i) for i in range(config.SIMILARITY_MIN_LIBRARY_SIZE - 1)]
    rng = np.random.default_rng(0)
    matches = rank_similar(
        draft_brain=rng.standard_normal(POOLED_DIM).astype(np.float32),
        draft_text=rng.standard_normal(EMBED_DIM).astype(np.float32),
        draft_roi_means=rng.standard_normal(3).astype(np.float32),
        library=library,
    )
    assert matches == []


def test_rank_similar_top_k_and_self_match():
    rng = np.random.default_rng(42)
    library = [_make_entry(i) for i in range(10)]
    target = library[3]

    matches = rank_similar(
        draft_brain=target.tribe_pooled,
        draft_text=target.text_embedding,
        draft_roi_means=target.roi_means,
        library=library,
        top_k=3,
    )
    assert len(matches) == 3
    assert matches[0]["video_id"] == target.video_id
    # Self-cosine must be near 1 (allow float32 noise).
    assert matches[0]["score"] > 0.95
    # ROI breakdown has all 3 keys; values bounded in [-1.001, 1.001] for cos.
    for m in matches:
        assert set(m["roi_breakdown"].keys()) == {"visual", "auditory", "language"}
        for v in m["roi_breakdown"].values():
            assert -1.001 <= v <= 1.001
        assert m["dominant_roi"] in ("visual", "auditory", "language")


def test_rank_similar_validates_input_shapes():
    library = [_make_entry(i) for i in range(5)]
    with pytest.raises(ValueError):
        rank_similar(
            draft_brain=np.zeros(POOLED_DIM - 1, dtype=np.float32),
            draft_text=np.zeros(EMBED_DIM, dtype=np.float32),
            draft_roi_means=np.zeros(3, dtype=np.float32),
            library=library,
        )
    with pytest.raises(ValueError):
        rank_similar(
            draft_brain=np.zeros(POOLED_DIM, dtype=np.float32),
            draft_text=np.zeros(EMBED_DIM + 1, dtype=np.float32),
            draft_roi_means=np.zeros(3, dtype=np.float32),
            library=library,
        )


def test_per_roi_similarity_identity():
    v = np.array([1.0, 2.0, -0.5], dtype=np.float32)
    sims = per_roi_similarity(v, v)
    # Identity gives the unit vector squared per axis but normalized: each (a*a)/(|v|^2).
    total = sum(sims.values())
    assert abs(total - 1.0) < 1e-4


def _entry_at(seed: int, days_ago: float, video_id: str | None = None, now: datetime | None = None) -> LibraryEntry:
    e = _make_entry(seed, video_id=video_id)
    base = now or datetime.now(timezone.utc)
    e.uploaded_at = (base - timedelta(days=days_ago)).isoformat(timespec="seconds")
    return e


def test_filter_candidates_default_caps_at_50():
    library = [_entry_at(seed=i, days_ago=i, video_id=f"v_{i:03d}") for i in range(120)]
    out = filter_candidates(library, last_n=50)
    assert len(out) == 50
    # Newest-first: v_000 (0 days ago) should be first, v_049 last.
    assert out[0].video_id == "v_000"
    assert out[-1].video_id == "v_049"


def test_filter_candidates_last_n_smaller_than_library():
    library = [_entry_at(seed=i, days_ago=i, video_id=f"v_{i:03d}") for i in range(20)]
    out = filter_candidates(library, last_n=5)
    assert [e.video_id for e in out] == ["v_000", "v_001", "v_002", "v_003", "v_004"]


def test_filter_candidates_since_days_only():
    now = datetime(2026, 4, 25, tzinfo=timezone.utc)
    library = [
        _entry_at(seed=1, days_ago=2, video_id="recent_a", now=now),
        _entry_at(seed=2, days_ago=5, video_id="recent_b", now=now),
        _entry_at(seed=3, days_ago=15, video_id="old_a", now=now),
        _entry_at(seed=4, days_ago=400, video_id="ancient", now=now),
    ]
    # Last week: only entries within 7 days.
    out = filter_candidates(library, last_n=None, since_days=7, now=now)
    assert {e.video_id for e in out} == {"recent_a", "recent_b"}
    # Last 3 months (~90 days): excludes ancient only.
    out = filter_candidates(library, last_n=None, since_days=90, now=now)
    assert {e.video_id for e in out} == {"recent_a", "recent_b", "old_a"}


def test_filter_candidates_since_days_then_last_n():
    now = datetime(2026, 4, 25, tzinfo=timezone.utc)
    library = [_entry_at(seed=i, days_ago=i, video_id=f"v_{i:02d}", now=now) for i in range(60)]
    # Past month (~30 days), capped to last 5.
    out = filter_candidates(library, last_n=5, since_days=30, now=now)
    assert len(out) == 5
    assert [e.video_id for e in out] == ["v_00", "v_01", "v_02", "v_03", "v_04"]


def test_filter_candidates_no_caps_returns_all():
    library = [_entry_at(seed=i, days_ago=i, video_id=f"v_{i:02d}") for i in range(10)]
    # last_n=None and last_n=0 both mean "no cap"; since_days=None → no time filter.
    assert len(filter_candidates(library, last_n=None, since_days=None)) == 10
    assert len(filter_candidates(library, last_n=0, since_days=None)) == 10


def test_filter_candidates_keeps_unparseable_when_no_time_filter():
    e = _make_entry(1, video_id="bad_iso")
    e.uploaded_at = "not a date"
    library = [e, _entry_at(seed=2, days_ago=1, video_id="good")]
    # No time filter → unparseable kept (sorted to tail).
    out = filter_candidates(library, last_n=None)
    assert {x.video_id for x in out} == {"bad_iso", "good"}
    # With time filter → unparseable dropped (can't decide).
    out = filter_candidates(library, last_n=None, since_days=7)
    assert {x.video_id for x in out} == {"good"}
