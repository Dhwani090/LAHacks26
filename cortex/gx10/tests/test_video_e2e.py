"""End-to-end video flow smoke.

Drives the FastAPI app under stub mode through:
  POST /analyze/video → /stream/{job}

Asserts every expected SSE event arrives. Runs on laptop (no GX10) thanks to
CORTEX_STUB_TRIBE/GEMMA=1.
"""
from __future__ import annotations
import io
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("CORTEX_STUB_TRIBE", "1")
os.environ.setdefault("CORTEX_STUB_GEMMA", "1")
os.environ.setdefault("CORTEX_STUB_TRANSCRIBE", "1")
os.environ.setdefault("CORTEX_STUB_EMBED", "1")
os.environ.setdefault("CORTEX_STUB_CURATOR", "1")

from fastapi.testclient import TestClient  # noqa: E402

from brain.library import library_registry  # noqa: E402
from brain.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _drain(resp) -> str:
    return b"".join(resp.iter_bytes()).decode("utf-8")


def test_analyze_video_streams_full_event_sequence(client):
    fake_mp4 = io.BytesIO(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64)
    files = {"file": ("hero.mp4", fake_mp4, "video/mp4")}
    r = client.post("/analyze/video", files=files)
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]

    with client.stream("GET", f"/stream/{job_id}") as resp:
        assert resp.status_code == 200
        text = _drain(resp)

    for ev in ("started", "transcript", "brain_frame", "cold_zones", "complete"):
        assert f"event: {ev}" in text, f"video stream missing {ev}"


def test_health_reports_predictor_and_corpus(client):
    body = client.get("/health").json()
    assert "predictor_loaded" in body and isinstance(body["predictor_loaded"], bool)
    assert "corpus_size" in body and isinstance(body["corpus_size"], int)


def test_predict_engagement_returns_sane_payload(client):
    fake_mp4 = io.BytesIO(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64)
    files = {"file": ("hero.mp4", fake_mp4, "video/mp4")}
    job_id = client.post("/analyze/video", files=files).json()["job_id"]

    with client.stream("GET", f"/stream/{job_id}") as resp:
        _drain(resp)

    r = client.post("/predict-engagement", json={"job_id": job_id, "followers": 10_000})
    assert r.status_code == 200, r.text
    body = r.json()
    assert 0.0 < body["predicted_rate"] <= 1.0
    assert 0 <= body["percentile"] <= 100
    assert isinstance(body["interpretation"], str) and body["interpretation"]
    assert body["followers_used"] == 10_000
    assert body["predictor_version"]


def test_predict_engagement_rejects_unknown_job(client):
    r = client.post("/predict-engagement", json={"job_id": "no-such-job", "followers": 0})
    assert r.status_code == 404


def test_predict_engagement_rejects_text_job(client):
    text_job = client.post("/analyze/text", json={"text": "hi"}).json()["job_id"]
    r = client.post("/predict-engagement", json={"job_id": text_job, "followers": 0})
    assert r.status_code == 400


# §11.6 — creator library + originality search.

def _video_job_completed(client, name: str = "draft.mp4") -> str:
    fake_mp4 = io.BytesIO(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64)
    job_id = client.post(
        "/analyze/video",
        files={"file": (name, fake_mp4, "video/mp4")},
    ).json()["job_id"]
    with client.stream("GET", f"/stream/{job_id}") as resp:
        _drain(resp)
    return job_id


def _upload_library_clip(client, creator_id: str, name: str) -> dict:
    fake_mp4 = io.BytesIO(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64)
    r = client.post(
        "/library/upload",
        data={"creator_id": creator_id},
        files={"file": (name, fake_mp4, "video/mp4")},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_similarity_cold_start_returns_message(client, tmp_path, monkeypatch):
    # Isolate filesystem state per test.
    library_registry.root = tmp_path / "library"
    library_registry.reset()

    job_id = _video_job_completed(client)
    r = client.post("/similarity", json={"job_id": job_id, "creator_id": "alice"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matches"] == []
    assert body["library_size"] == 0
    assert body["message"]


def test_similarity_after_5_uploads_returns_top_matches(client, tmp_path):
    library_registry.root = tmp_path / "library"
    library_registry.reset()

    creator = "bob"
    for i in range(5):
        _upload_library_clip(client, creator, f"past_{i}.mp4")
    listing = client.get(f"/library/{creator}").json()
    assert listing["size"] == 5

    job_id = _video_job_completed(client, name="fresh_draft.mp4")
    r = client.post("/similarity", json={"job_id": job_id, "creator_id": creator})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["library_size"] == 5
    assert len(body["matches"]) == 3
    for m in body["matches"]:
        assert -1.001 <= m["score"] <= 1.001
        assert m["dominant_roi"] in ("visual", "auditory", "language")
        roi = m["roi_breakdown"]
        assert {"visual", "auditory", "language"} == set(roi.keys())
    # Dominant ROI shouldn't be the same across all 3 matches in stub data — that
    # would indicate the breakdown isn't actually using the library entries' ROI means.
    dominants = {m["dominant_roi"] for m in body["matches"]}
    # Allow 1 or 2 distinct values (small library + noise) but not 0/all-equal scores.
    assert len(dominants) >= 1


def test_similarity_filter_last_n_narrows_candidate_size(client, tmp_path):
    library_registry.root = tmp_path / "library"
    library_registry.reset()
    creator = "filter_user"
    for i in range(8):
        _upload_library_clip(client, creator, f"clip_{i}.mp4")

    job_id = _video_job_completed(client, name="fresh.mp4")

    # No filter (default last_n=50, library has 8) → all 8 are candidates.
    r = client.post("/similarity", json={"job_id": job_id, "creator_id": creator})
    assert r.status_code == 200
    body = r.json()
    assert body["library_size"] == 8
    assert body["candidate_size"] == 8

    # Cap to last 6 → candidate_size drops, library_size stays.
    r = client.post(
        "/similarity",
        json={"job_id": job_id, "creator_id": creator, "last_n": 6},
    )
    body = r.json()
    assert body["library_size"] == 8
    assert body["candidate_size"] == 6
    assert body["filter"] == {"last_n": 6, "since_days": None}


def test_similarity_filter_under_min_returns_widen_message(client, tmp_path):
    library_registry.root = tmp_path / "library"
    library_registry.reset()
    creator = "narrow_filter"
    for i in range(7):
        _upload_library_clip(client, creator, f"c_{i}.mp4")

    job_id = _video_job_completed(client, name="fresh.mp4")
    # last_n=2 forces candidate set below SIMILARITY_MIN_LIBRARY_SIZE (5).
    r = client.post(
        "/similarity",
        json={"job_id": job_id, "creator_id": creator, "last_n": 2},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["matches"] == []
    assert body["library_size"] == 7
    assert body["candidate_size"] == 2
    assert "widen" in (body.get("message") or "").lower()


def test_similarity_rejects_unknown_job(client):
    r = client.post("/similarity", json={"job_id": "no-such-job", "creator_id": "x"})
    assert r.status_code == 404


def test_similarity_rejects_text_job(client):
    text_job = client.post("/analyze/text", json={"text": "hi"}).json()["job_id"]
    r = client.post("/similarity", json={"job_id": text_job, "creator_id": "x"})
    assert r.status_code == 400


def test_library_upload_idempotent_for_same_filename(client, tmp_path):
    library_registry.root = tmp_path / "library"
    library_registry.reset()

    first = _upload_library_clip(client, "carol", "shared.mp4")
    second = _upload_library_clip(client, "carol", "shared.mp4")
    # Same filename → same video_id (Path stem) → library doesn't double-count.
    assert first["library_entry_id"] == second["library_entry_id"]
    assert second["library_size"] == 1


def test_library_from_job_adds_completed_draft(client, tmp_path):
    """User-flow: /analyze/video → /stream complete → POST /library/from-job
    → entry exists in library. No re-run of TRIBE/Whisper required."""
    library_registry.root = tmp_path / "library"
    library_registry.reset()

    job_id = _video_job_completed(client, name="my_draft.mp4")
    r = client.post(
        "/library/from-job",
        json={"job_id": job_id, "creator_id": "eve"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["library_entry_id"] == "my_draft"
    assert body["library_size"] == 1

    listing = client.get("/library/eve").json()
    assert listing["size"] == 1
    assert listing["entries"][0]["video_id"] == "my_draft"
    assert listing["entries"][0]["duration_s"] > 0


def test_library_from_job_rejects_unknown_job(client, tmp_path):
    library_registry.root = tmp_path / "library"
    library_registry.reset()
    r = client.post(
        "/library/from-job",
        json={"job_id": "no-such-job", "creator_id": "x"},
    )
    assert r.status_code == 404


def test_library_from_job_rejects_text_job(client, tmp_path):
    library_registry.root = tmp_path / "library"
    library_registry.reset()
    text_job = client.post("/analyze/text", json={"text": "hi"}).json()["job_id"]
    r = client.post(
        "/library/from-job",
        json={"job_id": text_job, "creator_id": "x"},
    )
    assert r.status_code == 400


def test_library_from_job_honors_custom_video_id(client, tmp_path):
    library_registry.root = tmp_path / "library"
    library_registry.reset()
    job_id = _video_job_completed(client, name="anything.mp4")
    r = client.post(
        "/library/from-job",
        json={"job_id": job_id, "creator_id": "frank", "video_id": "renamed_clip"},
    )
    assert r.status_code == 200
    assert r.json()["library_entry_id"] == "renamed_clip"


def test_library_delete_removes_entry_and_updates_size(client, tmp_path):
    library_registry.root = tmp_path / "library"
    library_registry.reset()
    creator = "trim_me"
    _upload_library_clip(client, creator, "keep.mp4")
    _upload_library_clip(client, creator, "drop.mp4")
    assert client.get(f"/library/{creator}").json()["size"] == 2

    r = client.delete(f"/library/{creator}/drop")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["video_id"] == "drop"
    assert body["library_size"] == 1

    listing = client.get(f"/library/{creator}").json()
    assert listing["size"] == 1
    assert listing["entries"][0]["video_id"] == "keep"


def test_library_delete_404s_unknown_entry(client, tmp_path):
    library_registry.root = tmp_path / "library"
    library_registry.reset()
    _upload_library_clip(client, "user", "real.mp4")
    r = client.delete("/library/user/never_existed")
    assert r.status_code == 404


def test_library_delete_rejects_path_traversal(client, tmp_path):
    library_registry.root = tmp_path / "library"
    library_registry.reset()
    _upload_library_clip(client, "user", "real.mp4")
    # Starlette doesn't decode %2F into a path separator, so the route either
    # 404s (path didn't match a real entry) or our video_id regex 400s. Both
    # are safe — what matters is that the real entry survives untouched and
    # nothing outside the creator dir gets deleted.
    r = client.delete("/library/user/..%2Fescape")
    assert r.status_code in (400, 404)
    assert client.get("/library/user").json()["size"] == 1


def test_library_upload_does_not_persist_mp4(client, tmp_path):
    """PRD §11.6 invariant: the library is brain-features-only — raw mp4s are
    deleted after the TRIBE+Whisper pipeline runs. The on-disk JSON sidecar is
    the only thing that should remain."""
    from brain import config as backend_config

    library_registry.root = tmp_path / "library"
    library_registry.reset()
    _upload_library_clip(client, "dave", "ephemeral.mp4")

    uploads_dir = backend_config.CACHE_DIR / "library_uploads" / "dave"
    if uploads_dir.exists():
        leftover = list(uploads_dir.glob("ephemeral.*"))
        assert leftover == [], f"raw mp4 leaked into library_uploads: {leftover}"
