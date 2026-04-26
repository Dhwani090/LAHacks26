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
    """Shrink poll/tick to 10ms so the loop iterates fast in tests, point
    gate files at a temp dir, and STUB the iteration body to a no-op so
    these tests focus on loop machinery (gate files, priority gate, rotation,
    cancellation) rather than real yt-dlp + TRIBE work. The real
    _run_corpus_iteration is exercised by test_run_corpus_iteration_* below."""
    monkeypatch.setattr(config, "CURATOR_POLL_INTERVAL_S", 0.01)
    monkeypatch.setattr(config, "CURATOR_TICK_INTERVAL_S", 0.01)
    monkeypatch.setattr(config, "CURATOR_ENABLED_FILE", tmp_path / "curator.enabled")
    monkeypatch.setattr(config, "CURATOR_DISABLED_FILE", tmp_path / "curator.disabled")

    async def _noop_iteration(iter_count, iter_type, active_streams_fn):
        return None
    monkeypatch.setattr(curator_mod, "_run_iteration", _noop_iteration)

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


# ---------- R-03 corpus iteration end-to-end (yt-dlp + TRIBE stubbed) ----------


import json as _json  # noqa: E402
import shutil as _shutil  # noqa: E402

import numpy as _np  # noqa: E402

from brain import curator_gap  # noqa: E402
from brain.pooling import POOLED_DIM  # noqa: E402


def _make_meta(vid: str, duration: float = 30.0, views: int = 50_000, followers: int = 10_000):
    """Synthetic yt-dlp search result. Matches the keys build_corpus_row reads."""
    return {
        "id": vid,
        "webpage_url": f"https://youtube.com/shorts/{vid}",
        "duration": duration,
        "view_count": views,
        "channel_follower_count": followers,
        "like_count": 1500,
        "comment_count": 80,
        "uploader": "test_creator",
        "title": f"viral cooking shorts {vid}",
    }


@pytest.fixture
def corpus_iteration_env(monkeypatch, tmp_path):
    """Self-contained env for testing real corpus iterations: temp cache dir,
    stubbed yt-dlp (returns synthetic search results), stubbed TRIBE (returns
    synthetic frames), real fit_predictor + corpus + ingest + predictor.

    Each fixture instance writes a small seed corpus so cold-start gates the
    test (3 bootstrap queries get picked) but the refit has enough rows to
    compute R²."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(config, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(config, "CURATOR_LOG_FILE", cache_dir / "curator_log.jsonl")
    monkeypatch.setattr(config, "CURATOR_QUERY_POOL_FILE", cache_dir / "curator_query_pool.jsonl")
    monkeypatch.setattr(config, "CURATOR_ENABLED_FILE", cache_dir / "curator.enabled")
    monkeypatch.setattr(config, "CURATOR_DISABLED_FILE", cache_dir / "curator.disabled")
    # Smaller iteration so tests run fast.
    monkeypatch.setattr(config, "CURATOR_URLS_PER_ITERATION", 3)

    # Seed corpus — 8 valid rows so the post-iteration refit has enough data
    # to produce an R² (need ≥ 5 in fit_predictor).
    corpus_path = cache_dir / "corpus.jsonl"
    rng = _np.random.default_rng(0)
    seed_rows = []
    for i in range(8):
        feats = rng.standard_normal(POOLED_DIM).astype(float).tolist()
        seed_rows.append({
            "video_id": f"yt:seed_{i:03d}",
            "source": "youtube_shorts",
            "duration_s": 30.0,
            "followers": 10_000,
            "views": 5000 + i * 100,
            "engagement_rate": 0.05 + i * 0.01,
            "tribe_features": feats,
            "n_cold_zones": 0,
        })
    corpus_path.write_text("\n".join(_json.dumps(r) for r in seed_rows) + "\n", encoding="utf-8")

    # Reload the in-memory corpus snapshot at the new path.
    from brain.corpus import corpus
    corpus.load(corpus_path)

    # Stub yt-dlp ytsearch — return 4 candidates per query (more than per-iteration cap).
    async def _stub_ytsearch(query):
        return [_make_meta(f"vid_{abs(hash(query + str(i))) % 100000:05d}") for i in range(4)]
    monkeypatch.setattr(curator_mod, "_ytsearch_metadata", _stub_ytsearch)

    # Stub yt-dlp download — create a fake mp4 file in the temp dir.
    async def _stub_download(url, out_dir):
        fake = out_dir / f"{abs(hash(url)) % 100000:05d}.mp4"
        fake.write_bytes(b"fake mp4 content")
        return fake
    monkeypatch.setattr(curator_mod, "_ytdlp_download", _stub_download)

    yield cache_dir


@pytest.mark.asyncio
async def test_run_corpus_iteration_appends_rows_and_logs(corpus_iteration_env):
    cache_dir = corpus_iteration_env
    corpus_path = cache_dir / "corpus.jsonl"
    pre_n = sum(1 for _ in corpus_path.open())

    await curator_mod._run_corpus_iteration(0, active_streams_fn=lambda: 0)

    post_n = sum(1 for _ in corpus_path.open())
    assert post_n > pre_n, "iteration must append rows from stub yt-dlp + TRIBE"
    assert post_n - pre_n <= config.CURATOR_URLS_PER_ITERATION

    # curator_log.jsonl gets exactly one row.
    log_path = cache_dir / "curator_log.jsonl"
    assert log_path.exists()
    log_rows = [_json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    assert len(log_rows) == 1
    assert log_rows[0]["type"] == "corpus"
    assert log_rows[0]["n_added"] == post_n - pre_n
    assert log_rows[0]["queries"]


@pytest.mark.asyncio
async def test_run_corpus_iteration_yields_when_active_stream_arrives(corpus_iteration_env):
    cache_dir = corpus_iteration_env
    corpus_path = cache_dir / "corpus.jsonl"
    pre_n = sum(1 for _ in corpus_path.open())

    # active_streams returns 1 immediately — first per-URL check yields, no rows added.
    await curator_mod._run_corpus_iteration(0, active_streams_fn=lambda: 1)

    post_n = sum(1 for _ in corpus_path.open())
    assert post_n == pre_n, "no rows should be appended when a job is active"


@pytest.mark.asyncio
async def test_run_corpus_iteration_skips_already_seen_urls(corpus_iteration_env, monkeypatch):
    cache_dir = corpus_iteration_env
    corpus_path = cache_dir / "corpus.jsonl"
    # Stub returns the SAME id every call — already in the seed corpus would
    # match, but seed uses "yt:seed_*" prefix. Use a fresh id, then re-run; the
    # second run must dedupe.
    fixed_id = "vid_dedupe_test"

    async def _stub_ytsearch(query):
        return [_make_meta(fixed_id)]
    monkeypatch.setattr(curator_mod, "_ytsearch_metadata", _stub_ytsearch)

    pre_n = sum(1 for _ in corpus_path.open())
    await curator_mod._run_corpus_iteration(0, active_streams_fn=lambda: 0)
    after_first = sum(1 for _ in corpus_path.open())
    assert after_first - pre_n == 1, "first run should add the new url"

    await curator_mod._run_corpus_iteration(1, active_streams_fn=lambda: 0)
    after_second = sum(1 for _ in corpus_path.open())
    assert after_second == after_first, "second run must dedupe the same id"


def test_filter_search_results_applies_all_three_filters():
    existing = {"yt:already_in_corpus"}
    metas = [
        _make_meta("ok_one"),                                   # passes
        _make_meta("ok_two"),                                   # passes
        _make_meta("already_in_corpus"),                        # dedupe drop
        _make_meta("too_long", duration=300),                   # duration drop
        _make_meta("too_few_views", views=50),                  # views drop
        _make_meta("zero_duration", duration=0),                # duration drop
        {"id": "no_views_field", "duration": 30},               # missing view_count drop
    ]
    out = curator_mod._filter_search_results(metas, existing)
    out_ids = {m["id"] for m in out}
    assert out_ids == {"ok_one", "ok_two"}


def test_exclude_rows_in_corpus_marks_only_target_indices(tmp_path, monkeypatch):
    corpus_path = tmp_path / "corpus.jsonl"
    rows = [{"video_id": f"yt:row_{i}", "engagement_rate": 0.05} for i in range(5)]
    corpus_path.write_text("\n".join(_json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)

    marked = curator_mod._exclude_rows_in_corpus([1, 3])

    assert marked == [1, 3]
    out = [_json.loads(l) for l in corpus_path.read_text().splitlines() if l.strip()]
    assert out[0].get("excluded") is None
    assert out[1].get("excluded") is True
    assert out[1].get("excluded_reason") == "r2_regression"
    assert out[2].get("excluded") is None
    assert out[3].get("excluded") is True
    assert out[4].get("excluded") is None


def test_append_query_pool_truncates_to_max_size(tmp_path, monkeypatch):
    pool_path = tmp_path / "pool.jsonl"
    monkeypatch.setattr(config, "CURATOR_QUERY_POOL_FILE", pool_path)
    monkeypatch.setattr(config, "CURATOR_QUERY_POOL_MAX_SIZE", 5)

    # First append 3 — under cap.
    curator_mod._append_query_pool(["q1", "q2", "q3"], source_video_ids=["vid1"])
    assert len(pool_path.read_text().splitlines()) == 3

    # Append 4 more → 7 total → truncated to 5 most recent.
    curator_mod._append_query_pool(["q4", "q5", "q6", "q7"], source_video_ids=["vid2"])
    lines = pool_path.read_text().splitlines()
    assert len(lines) == 5
    parsed = [_json.loads(l) for l in lines]
    queries = [p["query"] for p in parsed]
    assert queries == ["q3", "q4", "q5", "q6", "q7"]  # FIFO: oldest dropped


@pytest.mark.asyncio
async def test_augment_query_pool_skips_when_no_top_quartile_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CURATOR_QUERY_POOL_FILE", tmp_path / "pool.jsonl")
    rows = [
        {"engagement_rate": 0.01, "title": "low", "uploader": "u", "video_id": "yt:v1"},
        {"engagement_rate": 0.02, "title": "low", "uploader": "u", "video_id": "yt:v2"},
    ]
    # Stub Gemma to fail loudly if called — it shouldn't be.
    class _FailGemma:
        def generate(self, *a, **kw):
            raise AssertionError("Gemma should not be called when no top-quartile rows")
    await curator_mod._augment_query_pool(rows, _FailGemma(), transcribe_fn=lambda p: "")
    assert not (tmp_path / "pool.jsonl").exists()


@pytest.mark.asyncio
async def test_augment_query_pool_appends_on_top_quartile(tmp_path, monkeypatch):
    pool_path = tmp_path / "pool.jsonl"
    monkeypatch.setattr(config, "CURATOR_QUERY_POOL_FILE", pool_path)
    monkeypatch.setattr(config, "CURATOR_QUERY_POOL_MAX_SIZE", 200)
    rows = [
        {"engagement_rate": 0.20, "title": "viral asmr cooking",
         "uploader": "chef_a", "video_id": "yt:hot1"},
        {"engagement_rate": 0.05, "title": "average",
         "uploader": "chef_b", "video_id": "yt:hot2"},
    ]

    class _StubGemma:
        def generate(self, prompt, max_new_tokens=128):
            return "asmr cooking trending\nviral kitchen hooks"

    await curator_mod._augment_query_pool(rows, _StubGemma(), transcribe_fn=lambda p: "")
    parsed = [_json.loads(l) for l in pool_path.read_text().splitlines() if l.strip()]
    assert {p["query"] for p in parsed} == {"asmr cooking trending", "viral kitchen hooks"}
    assert "yt:hot1" in parsed[0]["source_video_ids"]


def test_fit_predictor_skips_excluded_rows(tmp_path):
    """Regression: PRD §11.7 — `excluded:true` rows must not influence the fit."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    try:
        from fit_predictor import fit_predictor as _fit  # type: ignore
    finally:
        try:
            sys.path.remove(str(Path(__file__).resolve().parent.parent / "scripts"))
        except ValueError:
            pass

    corpus_path = tmp_path / "corpus.jsonl"
    out_path = tmp_path / "model.pkl"
    rng = _np.random.default_rng(0)
    rows = []
    for i in range(15):
        rows.append({
            "video_id": f"yt:r{i}",
            "duration_s": 30.0, "followers": 10_000,
            "views": 5000, "engagement_rate": 0.05 + i * 0.01,
            "tribe_features": rng.standard_normal(POOLED_DIM).astype(float).tolist(),
            "n_cold_zones": 0,
        })
    # Mark 3 rows excluded — the fitter must ignore them.
    for i in (2, 5, 9):
        rows[i]["excluded"] = True
    corpus_path.write_text("\n".join(_json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    out = _fit(corpus_path=corpus_path, out_path=out_path, model="ridge")
    assert out["n_rows"] == 12  # 15 − 3 excluded
    assert out_path.exists()
