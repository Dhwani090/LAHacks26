"""End-to-end video flow smoke (P2-08).

Drives the FastAPI app under stub mode through the demo Beat 2+3 sequence:
  POST /analyze/video → /stream/{job} → POST /auto-improve → /stream-improve/{job}
twice (V1→V2→V3). Asserts every expected SSE event arrives.

Runs on laptop (no GX10) thanks to CORTEX_STUB_TRIBE/GEMMA=1.
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
    # Fake mp4 — backend in stub mode never reads the bytes.
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


def test_auto_improve_v1_to_v2_to_v3(client):
    for round_idx, version in enumerate([1, 2], start=1):
        r = client.post("/auto-improve", json={"clip_id": "khan", "version": version})
        assert r.status_code == 200, f"round {round_idx}: {r.text}"
        job_id = r.json()["job_id"]

        with client.stream("GET", f"/stream-improve/{job_id}") as resp:
            assert resp.status_code == 200
            text = _drain(resp)

        for ev in (
            "reasoning",
            "cutting",
            "cut_applied",
            "reanalyzing",
            "brain_frame",
            "complete",
        ):
            assert f"event: {ev}" in text, f"round {round_idx} missing {ev}"


def test_full_demo_path(client):
    """Beat 2 + Beat 3 fused: analyze hero video then auto-improve twice."""
    files = {"file": ("hero.mp4", io.BytesIO(b"\x00" * 256), "video/mp4")}
    r = client.post("/analyze/video", files=files)
    assert r.status_code == 200
    analyze_job = r.json()["job_id"]

    with client.stream("GET", f"/stream/{analyze_job}") as resp:
        assert resp.status_code == 200
        _drain(resp)

    for version in (1, 2):
        ai = client.post("/auto-improve", json={"clip_id": "khan", "version": version})
        assert ai.status_code == 200
        with client.stream("GET", f"/stream-improve/{ai.json()['job_id']}") as resp:
            assert resp.status_code == 200
            text = _drain(resp)
        assert "event: complete" in text
