"""Tests for R-05 inspiration feed (PRD §11.8 — `GET /inspiration/{creator_id}`).

Covers compute_centroid (mean math + edge cases), load_trending_pool (filesystem
walk + skip rules), and the endpoint itself (cold-start gates, happy path,
path-traversal rejection, trending-extras merge).
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("CORTEX_STUB_TRIBE", "1")
os.environ.setdefault("CORTEX_STUB_GEMMA", "1")
os.environ.setdefault("CORTEX_STUB_TRANSCRIBE", "1")
os.environ.setdefault("CORTEX_STUB_EMBED", "1")
os.environ.setdefault("CORTEX_STUB_CURATOR", "1")

from fastapi.testclient import TestClient  # noqa: E402

from brain import config  # noqa: E402
from brain.library import (  # noqa: E402
    LibraryEntry,
    compute_centroid,
    library_registry,
    load_trending_pool,
    now_iso,
)
from brain.main import app  # noqa: E402
from brain.pooling import POOLED_DIM  # noqa: E402
from brain.text_embed import EMBED_DIM  # noqa: E402


# ---------- compute_centroid ----------


def _entry(seed: int, video_id: str | None = None) -> LibraryEntry:
    rng = np.random.default_rng(seed)
    text = rng.standard_normal(EMBED_DIM).astype(np.float32)
    text /= float(np.linalg.norm(text))
    return LibraryEntry(
        video_id=video_id or f"vid_{seed:03d}",
        uploaded_at=now_iso(),
        duration_s=30.0,
        tribe_pooled=rng.standard_normal(POOLED_DIM).astype(np.float32),
        roi_means=rng.standard_normal(3).astype(np.float32),
        transcript=f"transcript {seed}",
        text_embedding=text,
    )


def test_compute_centroid_empty_library_raises():
    with pytest.raises(ValueError):
        compute_centroid([])


def test_compute_centroid_single_entry_returns_normalized_vectors():
    e = _entry(seed=7)
    cb, ct, cr = compute_centroid([e])
    assert cb.shape == (POOLED_DIM,)
    assert ct.shape == (EMBED_DIM,)
    assert cr.shape == (3,)
    # text_embedding is already L2-normalized in _entry; centroid should match it (modulo float noise).
    np.testing.assert_allclose(ct, e.text_embedding, atol=1e-5)
    # brain centroid is L2-normalized version of the single entry.
    expected_brain = e.tribe_pooled / float(np.linalg.norm(e.tribe_pooled))
    np.testing.assert_allclose(cb, expected_brain, atol=1e-5)


def test_compute_centroid_n_entries_is_l2_normed_mean():
    library = [_entry(seed=i) for i in range(8)]
    cb, ct, _ = compute_centroid(library)
    # Centroid is a unit vector (L2 norm ≈ 1) for both brain and text.
    assert abs(float(np.linalg.norm(cb)) - 1.0) < 1e-5
    assert abs(float(np.linalg.norm(ct)) - 1.0) < 1e-5
    # And it's actually the mean (not some other reduction).
    expected_brain_raw = np.mean(np.stack([e.tribe_pooled for e in library]), axis=0)
    expected_brain = expected_brain_raw / float(np.linalg.norm(expected_brain_raw))
    np.testing.assert_allclose(cb, expected_brain, atol=1e-5)


def test_compute_centroid_handles_all_zero_means_without_nan():
    """Degenerate corpus where vectors sum to zero — _l2 falls through to zero, no NaN."""
    e_pos = _entry(seed=1)
    # Force a zero-summing pair: one vector and its negative.
    e_neg = LibraryEntry(
        video_id="neg",
        uploaded_at=now_iso(),
        duration_s=30.0,
        tribe_pooled=-e_pos.tribe_pooled,
        roi_means=-e_pos.roi_means,
        transcript="",
        text_embedding=-e_pos.text_embedding,
    )
    cb, ct, cr = compute_centroid([e_pos, e_neg])
    assert not np.any(np.isnan(cb))
    assert not np.any(np.isnan(ct))
    assert not np.any(np.isnan(cr))
    # Both centroid_brain and centroid_text should be the zero vector.
    np.testing.assert_allclose(cb, np.zeros(POOLED_DIM), atol=1e-6)
    np.testing.assert_allclose(ct, np.zeros(EMBED_DIM), atol=1e-6)


# ---------- load_trending_pool ----------


def _trending_blob(vid: str, *, valid_text: bool = True, valid_shape: bool = True) -> dict:
    rng = np.random.default_rng(hash(vid) & 0xFFFF)
    text = rng.standard_normal(EMBED_DIM).astype(np.float32) if valid_text else np.zeros(EMBED_DIM, dtype=np.float32)
    pooled_dim = POOLED_DIM if valid_shape else POOLED_DIM - 1
    return {
        "video_id": f"yt:{vid}",
        "uploaded_at": now_iso(),
        "duration_s": 30.0,
        "tribe_pooled": rng.standard_normal(pooled_dim).astype(np.float32).tolist(),
        "roi_means": rng.standard_normal(3).astype(np.float32).tolist(),
        "transcript": "" if not valid_text else f"trans {vid}",
        "text_embedding": text.tolist(),
        "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        "source_url": f"https://youtube.com/shorts/{vid}",
        "creator_handle": f"creator_{vid}",
        "view_count": 50_000,
        "engagement_rate": 0.12,
    }


def test_load_trending_pool_missing_dir(tmp_path):
    entries, extras = load_trending_pool(tmp_path / "does_not_exist")
    assert entries == []
    assert extras == {}


def test_load_trending_pool_walks_all_partitions(tmp_path):
    for date_name, ids in [("2026-04-23", ["a", "b"]), ("2026-04-24", ["c"]), ("2026-04-25", ["d", "e"])]:
        d = tmp_path / date_name
        d.mkdir()
        for vid in ids:
            (d / f"{vid}.json").write_text(json.dumps(_trending_blob(vid)))

    entries, extras = load_trending_pool(tmp_path)
    assert len(entries) == 5
    assert {e.video_id for e in entries} == {"yt:a", "yt:b", "yt:c", "yt:d", "yt:e"}
    # Extras dict is keyed by video_id and has trending-specific fields.
    for vid in ("yt:a", "yt:e"):
        assert extras[vid]["source_url"].endswith(f"/{vid.split(':')[1]}")
        assert extras[vid]["creator_handle"].startswith("creator_")
        assert extras[vid]["view_count"] == 50_000
        assert extras[vid]["engagement_rate"] == pytest.approx(0.12)


def test_load_trending_pool_skips_zero_text_embedding(tmp_path):
    d = tmp_path / "2026-04-25"
    d.mkdir()
    (d / "good.json").write_text(json.dumps(_trending_blob("good")))
    (d / "empty.json").write_text(json.dumps(_trending_blob("empty", valid_text=False)))

    entries, extras = load_trending_pool(tmp_path)
    assert len(entries) == 1
    assert entries[0].video_id == "yt:good"
    assert "yt:empty" not in extras


def test_load_trending_pool_skips_malformed_entries(tmp_path):
    d = tmp_path / "2026-04-25"
    d.mkdir()
    (d / "good.json").write_text(json.dumps(_trending_blob("good")))
    (d / "bad_shape.json").write_text(json.dumps(_trending_blob("bad", valid_shape=False)))
    (d / "not_json.json").write_text("{ not valid json")

    entries, extras = load_trending_pool(tmp_path)
    assert len(entries) == 1
    assert entries[0].video_id == "yt:good"


# ---------- /inspiration endpoint ----------


@pytest.fixture
def inspiration_env(monkeypatch, tmp_path):
    """Isolate the test's library + trending dirs from the real cache/."""
    library_root = tmp_path / "library"
    trending_dir = tmp_path / "trending"
    library_root.mkdir()
    trending_dir.mkdir()
    monkeypatch.setattr(config, "CURATOR_TRENDING_DIR", trending_dir)
    monkeypatch.setattr(library_registry, "root", library_root)
    monkeypatch.setattr(library_registry, "_libraries", {})  # clear cache
    yield library_root, trending_dir


def _seed_library(library_root: Path, creator_id: str, n: int) -> None:
    creator_dir = library_root / creator_id
    creator_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        e = _entry(seed=i, video_id=f"clip_{i:03d}")
        (creator_dir / f"{e.video_id}.json").write_text(json.dumps(e.to_json()))


def _seed_trending(trending_dir: Path, n: int) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_dir = trending_dir / today
    today_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        vid = f"trend_{i:03d}"
        (today_dir / f"{vid}.json").write_text(json.dumps(_trending_blob(vid)))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_inspiration_cold_start_library_too_small(client, inspiration_env):
    library_root, trending_dir = inspiration_env
    _seed_library(library_root, "demo", n=2)  # under MIN
    _seed_trending(trending_dir, n=10)

    r = client.get("/inspiration/demo")
    assert r.status_code == 200
    body = r.json()
    assert body["recommendations"] == []
    assert body["library_size"] == 2
    assert "upload at least" in body["message"]


def test_inspiration_empty_trending_pool(client, inspiration_env):
    library_root, _trending_dir = inspiration_env
    _seed_library(library_root, "demo", n=8)
    # Trending dir exists but empty → expect "trending not populated" message.

    r = client.get("/inspiration/demo")
    assert r.status_code == 200
    body = r.json()
    assert body["recommendations"] == []
    assert body["library_size"] == 8
    assert body["trending_pool_size"] == 0
    assert "trending pool" in body["message"].lower()


def test_inspiration_happy_path_returns_top_3(client, inspiration_env):
    library_root, trending_dir = inspiration_env
    _seed_library(library_root, "demo", n=8)
    _seed_trending(trending_dir, n=10)

    r = client.get("/inspiration/demo")
    assert r.status_code == 200
    body = r.json()
    assert body["library_size"] == 8
    assert body["trending_pool_size"] == 10
    assert body["creator_id"] == "demo"
    assert body["message"] is None
    recs = body["recommendations"]
    assert len(recs) == config.SIMILARITY_TOP_K
    # Each rec must have the full shape per PRD §11.8.
    for rec in recs:
        for key in (
            "video_id", "score", "thumbnail_url", "source_url", "uploaded_at",
            "creator_handle", "view_count", "engagement_rate",
            "dominant_roi", "roi_breakdown",
        ):
            assert key in rec, f"missing key: {key}"
        assert rec["dominant_roi"] in ("visual", "auditory", "language")
        # Trending extras flow through.
        assert rec["source_url"].startswith("https://youtube.com/shorts/")
        assert rec["creator_handle"].startswith("creator_")
        assert rec["view_count"] == 50_000


def test_inspiration_rejects_path_traversal(client, inspiration_env):
    r = client.get("/inspiration/..%2Fescape")
    # Either 400 from regex (preferred) or 404 from Starlette path resolution.
    # The library file/dir for "..%2Fescape" must NOT have been touched.
    assert r.status_code in (400, 404)
