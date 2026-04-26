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

from fastapi.testclient import TestClient  # noqa: E402

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
