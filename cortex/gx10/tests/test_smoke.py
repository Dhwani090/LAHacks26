# Smoke tests — runs against the FastAPI app with stubs.
# PRD §8 verification + CLAUDE.md §5 (`pytest tests/test_smoke.py -v`).
# Requires CORTEX_STUB_TRIBE=1 + CORTEX_STUB_GEMMA=1 to skip real model loads.
# See cortex/gx10/brain/main.py.

import os
import sys
from pathlib import Path

# Allow `from brain import ...` when run from gx10/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("CORTEX_STUB_TRIBE", "1")
os.environ.setdefault("CORTEX_STUB_GEMMA", "1")

from fastapi.testclient import TestClient  # noqa: E402

from brain.main import app  # noqa: E402

# Use context manager so FastAPI lifespan fires (loads stubs).
import pytest  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    assert body["tribe_loaded"] is True
    assert body["gemma_loaded"] is True


def test_analyze_text_returns_job_id(client):
    r = client.post("/analyze/text", json={"text": "hero text for smoke test"})
    assert r.status_code == 200
    assert r.json()["mode"] == "text"
    assert r.json()["job_id"]


def test_stream_text_emits_events(client):
    job_id = client.post("/analyze/text", json={"text": "hero"}).json()["job_id"]
    with client.stream("GET", f"/stream/{job_id}") as resp:
        assert resp.status_code == 200
        body = b"".join(resp.iter_bytes())
    text = body.decode("utf-8")
    for ev in ("started", "brain_frame", "cold_zones", "complete"):
        assert f"event: {ev}" in text, f"missing event {ev}"
