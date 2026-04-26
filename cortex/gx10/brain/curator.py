# NemoClaw idle-time curator — active-learning loop on the GX10.
# Implements PRD §11.7 (corpus iterations + trending iterations rotated 5:1)
# and PRD §11.8 (trending pool harvested on iter_count % 6 == 5).
# R-01 scope: skeleton + lifespan + status endpoint. Iteration body is a no-op;
# R-02 wires query selection, R-03 wires scrape+refit, R-04 splits trending mode.
# See docs/PRD.md §11.7.

from __future__ import annotations
import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from . import config

logger = logging.getLogger(__name__)


@dataclass
class CuratorState:
    """Mutable state owned by the curator loop. Read-only from /curator/status."""
    running: bool = False
    iter_count: int = 0
    last_iter_at: str | None = None
    last_iter_type: str | None = None
    paused_for_jobs: bool = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iter_type_for(iter_count: int) -> str:
    """Rotation: 5 corpus iterations, then 1 trending. iter 0..4 = corpus, iter 5 = trending."""
    if iter_count % config.CURATOR_ITERATIONS_PER_TRENDING == config.CURATOR_ITERATIONS_PER_TRENDING - 1:
        return "trending"
    return "corpus"


def _enabled() -> bool:
    """Master gate — curator only runs when this file exists. Off by default for Phase 0–3."""
    return config.CURATOR_ENABLED_FILE.exists()


def _kill_switch() -> bool:
    """Runtime emergency stop. Takes precedence over the enabled file."""
    return config.CURATOR_DISABLED_FILE.exists()


async def curator_loop(active_streams_fn: Callable[[], int]) -> None:
    """Long-running coroutine started by the FastAPI lifespan.

    Cancellation: lifespan shutdown calls .cancel() on the task — we propagate
    CancelledError after marking running=False so /curator/status reflects the exit.
    """
    state = CURATOR_STATE
    state.running = True
    logger.info("curator: loop started (poll=%ss, tick=%ss, rotation=1:%s)",
                config.CURATOR_POLL_INTERVAL_S,
                config.CURATOR_TICK_INTERVAL_S,
                config.CURATOR_ITERATIONS_PER_TRENDING)
    try:
        while True:
            # Kill switch wins over enable. Check both at top of every iteration so a
            # `touch cache/curator.disabled` halts within one poll interval.
            if _kill_switch():
                logger.info("curator: cache/curator.disabled present — idle")
                state.paused_for_jobs = False
                await asyncio.sleep(config.CURATOR_POLL_INTERVAL_S)
                continue
            if not _enabled():
                # Off by default for Phase 0–3 — touch cache/curator.enabled to wake.
                state.paused_for_jobs = False
                await asyncio.sleep(config.CURATOR_POLL_INTERVAL_S)
                continue

            # Priority gate — yield to live `/analyze/*` requests.
            active = active_streams_fn()
            if active > 0:
                state.paused_for_jobs = True
                logger.debug("curator: %d active streams — sleeping %ss",
                             active, config.CURATOR_POLL_INTERVAL_S)
                await asyncio.sleep(config.CURATOR_POLL_INTERVAL_S)
                continue
            state.paused_for_jobs = False

            iter_type = _iter_type_for(state.iter_count)
            await _run_iteration(state.iter_count, iter_type)
            state.iter_count += 1
            state.last_iter_at = _now_iso()
            state.last_iter_type = iter_type

            await asyncio.sleep(config.CURATOR_TICK_INTERVAL_S)
    except asyncio.CancelledError:
        logger.info("curator: cancelled — shutting down")
        raise
    finally:
        state.running = False


async def _run_iteration(iter_count: int, iter_type: str) -> None:
    """Iteration body. R-01 = no-op (logs and returns). R-02 fills query selection,
    R-03 fills scrape+refit, R-04 splits the corpus vs trending terminal step."""
    logger.info("curator: iter=%d type=%s (no-op — R-02/R-03 not implemented)",
                iter_count, iter_type)


# Module-level singleton — one curator per process.
CURATOR_STATE = CuratorState()


def reset_state_for_test() -> None:
    """Tests reset the singleton between runs. Not for production callers."""
    CURATOR_STATE.running = False
    CURATOR_STATE.iter_count = 0
    CURATOR_STATE.last_iter_at = None
    CURATOR_STATE.last_iter_type = None
    CURATOR_STATE.paused_for_jobs = False


def is_stub() -> bool:
    """When CORTEX_STUB_CURATOR=1, the lifespan skips spawning the loop entirely.
    Tests that don't care about the curator (e.g. existing smoke tests) set this."""
    return os.environ.get("CORTEX_STUB_CURATOR") == "1"
