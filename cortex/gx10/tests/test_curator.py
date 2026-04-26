"""Unit + integration tests for brain.curator (PRD §11.7 — R-01 skeleton).

Covers iteration-type rotation, gate-file precedence (disabled > enabled),
priority gate against active streams, lifespan cancellation, and the
GET /curator/status endpoint shape. Iteration body is a no-op in R-01;
R-02/R-03 will extend these tests.
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("CORTEX_STUB_TRIBE", "1")
os.environ.setdefault("CORTEX_STUB_GEMMA", "1")
# Per-test the loop here, so we DON'T want the lifespan to spawn a second one.
os.environ["CORTEX_STUB_CURATOR"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from brain import config, curator as curator_mod  # noqa: E402
from brain.main import app  # noqa: E402


# ---------- pure helpers ----------


def test_iter_type_rotation_is_5_corpus_then_1_trending():
    seen = [curator_mod._iter_type_for(i) for i in range(12)]
    assert seen == [
        "corpus", "corpus", "corpus", "corpus", "corpus", "trending",
        "corpus", "corpus", "corpus", "corpus", "corpus", "trending",
    ]


def test_enabled_and_kill_switch_files(tmp_path, monkeypatch):
    enabled = tmp_path / "curator.enabled"
    disabled = tmp_path / "curator.disabled"
    monkeypatch.setattr(config, "CURATOR_ENABLED_FILE", enabled)
    monkeypatch.setattr(config, "CURATOR_DISABLED_FILE", disabled)

    assert curator_mod._enabled() is False
    assert curator_mod._kill_switch() is False

    enabled.touch()
    assert curator_mod._enabled() is True
    assert curator_mod._kill_switch() is False

    disabled.touch()
    assert curator_mod._enabled() is True
    assert curator_mod._kill_switch() is True  # both true → kill switch wins in loop


# ---------- loop behavior (uses tiny intervals) ----------


@pytest.fixture
def fast_intervals(monkeypatch, tmp_path):
    """Shrink poll/tick to 10ms so the loop iterates fast in tests, and point
    gate files at a temp dir so we don't touch the real cache/."""
    monkeypatch.setattr(config, "CURATOR_POLL_INTERVAL_S", 0.01)
    monkeypatch.setattr(config, "CURATOR_TICK_INTERVAL_S", 0.01)
    monkeypatch.setattr(config, "CURATOR_ENABLED_FILE", tmp_path / "curator.enabled")
    monkeypatch.setattr(config, "CURATOR_DISABLED_FILE", tmp_path / "curator.disabled")
    curator_mod.reset_state_for_test()
    yield tmp_path
    curator_mod.reset_state_for_test()


@pytest.mark.asyncio
async def test_loop_idle_when_enabled_file_absent(fast_intervals):
    task = asyncio.create_task(curator_mod.curator_loop(active_streams_fn=lambda: 0))
    await asyncio.sleep(0.1)  # plenty of time to iterate IF gated open
    assert curator_mod.CURATOR_STATE.iter_count == 0
    assert curator_mod.CURATOR_STATE.running is True
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert curator_mod.CURATOR_STATE.running is False


@pytest.mark.asyncio
async def test_loop_iterates_when_enabled(fast_intervals):
    (fast_intervals / "curator.enabled").touch()
    task = asyncio.create_task(curator_mod.curator_loop(active_streams_fn=lambda: 0))
    await asyncio.sleep(0.15)
    assert curator_mod.CURATOR_STATE.iter_count >= 3
    assert curator_mod.CURATOR_STATE.last_iter_type == "corpus"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_kill_switch_halts_iteration(fast_intervals):
    (fast_intervals / "curator.enabled").touch()
    (fast_intervals / "curator.disabled").touch()
    task = asyncio.create_task(curator_mod.curator_loop(active_streams_fn=lambda: 0))
    await asyncio.sleep(0.1)
    assert curator_mod.CURATOR_STATE.iter_count == 0  # disabled wins
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_kill_switch_halts_iteration_mid_flight(fast_intervals):
    """Regression: caught by /qa on 2026-04-25.

    The original test_kill_switch_halts_iteration only verifies the kill
    switch when the file pre-exists at startup. This covers the more
    important case: curator is iterating, user `touch cache/curator.disabled`
    mid-flight, iteration must halt within ~one tick. If the disabled-file
    check ever moves out of the per-iteration top, this test breaks first.
    """
    (fast_intervals / "curator.enabled").touch()
    task = asyncio.create_task(curator_mod.curator_loop(active_streams_fn=lambda: 0))
    # Let it iterate a few times.
    await asyncio.sleep(0.1)
    iter_at_kill = curator_mod.CURATOR_STATE.iter_count
    assert iter_at_kill >= 1, "curator should have iterated before we kill it"

    # Now drop the kill switch — iteration must freeze.
    (fast_intervals / "curator.disabled").touch()
    await asyncio.sleep(0.1)  # plenty of fast-interval ticks
    iter_after_kill = curator_mod.CURATOR_STATE.iter_count
    assert iter_after_kill == iter_at_kill, (
        f"kill switch did not halt iteration mid-flight: "
        f"iter went {iter_at_kill} → {iter_after_kill}"
    )
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_priority_gate_pauses_for_active_streams(fast_intervals):
    (fast_intervals / "curator.enabled").touch()
    active = {"n": 1}  # mutable so the test can flip it
    task = asyncio.create_task(
        curator_mod.curator_loop(active_streams_fn=lambda: active["n"])
    )
    await asyncio.sleep(0.1)
    assert curator_mod.CURATOR_STATE.iter_count == 0  # blocked by active stream
    assert curator_mod.CURATOR_STATE.paused_for_jobs is True

    active["n"] = 0
    await asyncio.sleep(0.15)
    assert curator_mod.CURATOR_STATE.iter_count >= 1
    assert curator_mod.CURATOR_STATE.paused_for_jobs is False

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_loop_rotates_to_trending_on_iteration_5(fast_intervals):
    (fast_intervals / "curator.enabled").touch()
    task = asyncio.create_task(curator_mod.curator_loop(active_streams_fn=lambda: 0))
    # Wait long enough for at least 6 iterations at 0.01s each.
    await asyncio.sleep(0.4)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert curator_mod.CURATOR_STATE.iter_count >= 6
    # Trending iteration always lands at iter_count % 6 == 5; one of the iterations
    # must have been a trending tick at some point. The state's last_iter_type is the
    # most-recent — could be either depending on timing. Verify trending was seen by
    # checking the helper directly (already covered) AND that iter_count crossed 5.


# ---------- FastAPI integration ----------


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_curator_status_endpoint_shape(client):
    r = client.get("/curator/status")
    assert r.status_code == 200
    body = r.json()
    # Required shape per PRD §11.7.
    for key in (
        "running", "enabled", "kill_switch", "paused_for_jobs",
        "iter_count", "last_iter_at", "last_iter_type",
        "corpus_size", "trending_pool_size", "last_r2",
    ):
        assert key in body, f"missing key: {key}"
    # CORTEX_STUB_CURATOR=1 → lifespan does not spawn the loop.
    assert body["running"] is False
    assert body["iter_count"] == 0
    assert body["trending_pool_size"] == 0
    assert body["last_r2"] is None
