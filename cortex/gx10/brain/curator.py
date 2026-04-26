# NemoClaw idle-time curator — active-learning loop on the GX10.
# Implements PRD §11.7 (corpus iterations + trending iterations rotated 5:1)
# and PRD §11.8 (trending pool harvested on iter_count % 6 == 5).
# R-01: skeleton + lifespan + status endpoint. R-02: query selection.
# R-03: this file — yt-dlp ytsearch + filter + per-URL TRIBE + corpus append +
# in-process refit + R²-rollback + self-supervised query expansion.
# R-04 will split the trending iteration's terminal step (write to cache/trending/).
# See docs/PRD.md §11.7.

from __future__ import annotations
import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

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
            await _run_iteration(state.iter_count, iter_type, active_streams_fn)
            state.iter_count += 1
            state.last_iter_at = _now_iso()
            state.last_iter_type = iter_type

            await asyncio.sleep(config.CURATOR_TICK_INTERVAL_S)
    except asyncio.CancelledError:
        logger.info("curator: cancelled — shutting down")
        raise
    finally:
        state.running = False


# ---------------------------------------------------------------------------
# Iteration bodies (R-03 corpus end-to-end; R-04 will fill trending terminal).
# ---------------------------------------------------------------------------


async def _run_iteration(
    iter_count: int,
    iter_type: str,
    active_streams_fn: Callable[[], int],
) -> None:
    """Dispatch to corpus or trending iteration. R-04 will replace the trending
    branch's call site with a real cache/trending/ writer; for R-03 trending
    iterations log a no-op (the data flow is identical except the terminal step)."""
    logger.info("curator: iter=%d type=%s — start", iter_count, iter_type)
    if iter_type == "corpus":
        await _run_corpus_iteration(iter_count, active_streams_fn)
    else:
        await _run_trending_iteration(iter_count, active_streams_fn)


async def _run_corpus_iteration(
    iter_count: int,
    active_streams_fn: Callable[[], int],
) -> None:
    """End-to-end corpus iteration (PRD §11.7 steps 2-6).

    Pipeline:
      1. Pick queries via curator_gap.pick_queries (R-02).
      2. ytsearch20:<query> per query → metadata-only candidate pool, filter
         (duration ≤ 180s, view_count > 1000, dedupe vs corpus).
      3. For each picked URL up to CURATOR_URLS_PER_ITERATION:
         a. Re-check active_streams — if a job arrived mid-iteration, stop and
            yield (live inference always wins).
         b. yt-dlp -f mp4 → temp dir.
         c. Acquire TRIBE lock → analyze_video → pool features.
         d. Append corpus row.
      4. If ≥ 1 row was appended, snapshot pickle + refit + compute R² + rollback
         if regression > CURATOR_R2_REGRESSION_THRESHOLD.
      5. Write iteration log row to cache/curator_log.jsonl.
      6. If iteration produced top-quartile rows, ask Gemma for new query
         candidates; append to cache/curator_query_pool.jsonl (FIFO cap).
    """
    # Lazy imports — keep module-level imports clean and let CORTEX_STUB_*
    # tests skip the heavy modules entirely.
    from . import curator_gap
    from .corpus import corpus
    from .gemma import gemma_service
    from .ingest import append_corpus_row, build_corpus_row, read_existing_video_ids
    from .pooling import frames_to_array, pool_tribe_output
    from .predictor import predictor
    from .tribe import tribe_service
    from .transcribe import transcribe

    iter_log: dict[str, Any] = {
        "ts": _now_iso(),
        "iter": iter_count,
        "type": "corpus",
        "queries": [],
        "n_added": 0,
        "n_excluded": 0,
        "r2_before": None,
        "r2_after": None,
    }

    queries = curator_gap.pick_queries(
        iter_type="corpus",
        corpus=corpus,
        predictor=predictor,
        gemma=gemma_service,
        query_pool_path=config.CURATOR_QUERY_POOL_FILE,
    )
    iter_log["queries"] = queries
    logger.info("curator: iter=%d queries=%s", iter_count, queries)

    existing_ids = read_existing_video_ids(config.CACHE_DIR / "corpus.jsonl")

    # Collect candidate URLs from ALL queries first (so we can dedupe across queries),
    # then process up to the per-iteration cap.
    candidates: list[dict[str, Any]] = []
    for q in queries:
        try:
            metas = await _ytsearch_metadata(q)
        except Exception as exc:
            logger.error("curator: ytsearch failed for %r: %s", q, exc)
            continue
        for meta in _filter_search_results(metas, existing_ids):
            if meta["id"] in {c["id"] for c in candidates}:
                continue
            candidates.append(meta)
            if len(candidates) >= config.CURATOR_URLS_PER_ITERATION:
                break
        if len(candidates) >= config.CURATOR_URLS_PER_ITERATION:
            break

    logger.info("curator: iter=%d %d candidates after filter", iter_count, len(candidates))

    new_rows: list[dict[str, Any]] = []
    new_row_indices: list[int] = []  # 0-based index in corpus.jsonl post-append
    pre_append_n = sum(1 for _ in (config.CACHE_DIR / "corpus.jsonl").open()) if (config.CACHE_DIR / "corpus.jsonl").exists() else 0

    with tempfile.TemporaryDirectory(prefix="cortex_curator_") as tmp:
        tmp_dir = Path(tmp)
        for cand in candidates:
            # Yield if a live job arrived since we passed the priority gate.
            if active_streams_fn() > 0:
                logger.info("curator: iter=%d active streams → yielding mid-iteration", iter_count)
                break
            try:
                row = await _process_candidate(
                    cand, tmp_dir, tribe_service, frames_to_array, pool_tribe_output, build_corpus_row,
                )
            except Exception as exc:
                logger.error("curator: per-URL failed for %s: %s", cand.get("id"), exc)
                continue
            if row is None:
                continue
            append_corpus_row(config.CACHE_DIR / "corpus.jsonl", row)
            new_rows.append(row)
            new_row_indices.append(pre_append_n + len(new_rows) - 1)

    iter_log["n_added"] = len(new_rows)

    # Refit + R² rollback (PRD §11.7 step 6).
    if new_rows:
        iter_log["r2_before"] = predictor.r2
        rollback_excluded = await _refit_with_rollback(new_row_indices)
        iter_log["r2_after"] = predictor.r2
        iter_log["n_excluded"] = len(rollback_excluded)

    _append_log_row(iter_log)

    # Self-supervised query expansion — only on successful corpus iterations
    # with at least one top-quartile row (PRD §11.7 source 3).
    if new_rows and not iter_log["n_excluded"]:
        await _augment_query_pool(new_rows, gemma_service, transcribe)


# ---------------------------------------------------------------------------
# yt-dlp helpers (asyncio subprocess for native cancellation).
# ---------------------------------------------------------------------------


async def _ytsearch_metadata(query: str) -> list[dict[str, Any]]:
    """Run `yt-dlp ytsearch20:<query> -j --skip-download --no-warnings` and
    parse the resulting newline-delimited JSON. Each line is one search result's
    metadata dict (yt-dlp's flat extractor mode for ytsearch:)."""
    cmd = [*_ytdlp_cmd(), f"ytsearch20:{query}", "-j", "--skip-download", "--no-warnings"]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=config.CURATOR_YTSEARCH_TIMEOUT_S)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(f"ytsearch timed out for {query!r}")
    if proc.returncode != 0:
        raise RuntimeError(f"ytsearch failed: {stderr.decode('utf-8', 'replace')[:300]}")
    out: list[dict[str, Any]] = []
    for line in stdout.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _ytdlp_cmd() -> list[str]:
    """Same fallback chain as scripts/ingest_shorts.py — prefer the in-process
    Python module so we don't need yt-dlp on PATH inside containers."""
    import importlib.util  # local import — keeps module load light
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    binary = shutil.which("yt-dlp")
    if binary:
        return [binary]
    raise RuntimeError("yt-dlp not importable and not on PATH — pip install yt-dlp")


def _filter_search_results(
    metas: list[dict[str, Any]],
    existing_ids: set[str],
) -> list[dict[str, Any]]:
    """Apply the per-PRD §11.7 step 3 filters: duration ≤ MAX_CLIP_DURATION_S,
    view_count > CURATOR_MIN_VIEWS, and not already in the corpus (dedupe by
    `yt:<id>` matching brain.ingest.build_corpus_row's video_id format)."""
    keep: list[dict[str, Any]] = []
    for meta in metas:
        vid = meta.get("id")
        if not isinstance(vid, str):
            continue
        if f"yt:{vid}" in existing_ids:
            continue
        duration = meta.get("duration")
        if not isinstance(duration, (int, float)) or duration > config.MAX_CLIP_DURATION_S or duration <= 0:
            continue
        views = meta.get("view_count")
        if not isinstance(views, (int, float)) or views < config.CURATOR_MIN_VIEWS:
            continue
        keep.append(meta)
    return keep


async def _ytdlp_download(url: str, out_dir: Path) -> Path:
    """Async download via yt-dlp -f mp4. Returns the produced file path."""
    out_template = str(out_dir / "%(id)s.%(ext)s")
    cmd = [*_ytdlp_cmd(), "-f", "mp4/best", "-o", out_template, url, "--no-warnings"]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=config.CURATOR_DOWNLOAD_TIMEOUT_S)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(f"yt-dlp download timed out for {url}")
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp download failed: {stderr.decode('utf-8', 'replace')[:300]}")
    candidates = sorted(
        [p for p in out_dir.iterdir() if p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}],
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if not candidates:
        raise RuntimeError(f"yt-dlp succeeded but no media file in {out_dir}")
    return candidates[0]


# ---------------------------------------------------------------------------
# Per-candidate pipeline.
# ---------------------------------------------------------------------------


async def _process_candidate(
    meta: dict[str, Any],
    tmp_dir: Path,
    tribe_service: Any,
    frames_to_array: Callable[..., Any],
    pool_tribe_output: Callable[..., Any],
    build_corpus_row: Callable[..., Any],
) -> dict[str, Any] | None:
    """Download → TRIBE → pool → corpus row. mp4 deleted after extraction.

    Wrapped per-call in try/finally so a TRIBE crash still cleans the mp4."""
    url = meta.get("webpage_url") or meta.get("original_url") or f"https://youtube.com/shorts/{meta.get('id')}"
    video_path: Path | None = None
    try:
        video_path = await _ytdlp_download(url, tmp_dir)
        # TRIBE.predict is sync + not thread-safe — go through the lock and to_thread
        # so we don't stall the event loop while the model runs.
        async with tribe_service.lock:
            result = await asyncio.to_thread(tribe_service.analyze_video, video_path)
        arr = frames_to_array(result["brain_frames"])
        pooled = pool_tribe_output(arr)
        n_cold_zones = len(result.get("cold_zones") or [])
        return build_corpus_row(meta, pooled, n_cold_zones)
    finally:
        if video_path is not None and video_path.exists():
            try:
                video_path.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Refit + R² rollback (PRD §11.7 step 6).
# ---------------------------------------------------------------------------


async def _refit_with_rollback(new_row_indices: list[int]) -> list[int]:
    """Run fit_predictor in-process. If R² drops by more than the threshold,
    mark the just-appended rows `excluded:true` (audit trail) and restore the
    prior pickle. Returns the list of indices excluded (empty on no rollback).

    Snapshots the pickle to a sibling `.snapshot` file before refit so the
    rollback is a simple file copy. The corpus.jsonl is rewritten in place
    to set excluded:true on the affected rows; existing rows are untouched.
    """
    from .corpus import corpus
    from .predictor import EngagementPredictor, predictor

    pkl = config.CACHE_DIR / "engagement_predictor.pkl"
    snapshot = pkl.with_suffix(".pkl.snapshot")
    if pkl.exists():
        shutil.copy2(pkl, snapshot)

    r2_before = predictor.r2
    try:
        # Run the (CPU-bound) fit in a thread so it doesn't block the event loop.
        fit_result = await asyncio.to_thread(_invoke_fit_predictor, pkl)
    except Exception as exc:
        logger.error("curator: refit raised %s — restoring snapshot", exc)
        if snapshot.exists():
            shutil.copy2(snapshot, pkl)
        return _exclude_rows_in_corpus(new_row_indices)
    finally:
        # Reload the predictor singleton so live /predict-engagement sees the new model.
        if pkl.exists():
            try:
                loaded = EngagementPredictor.load(pkl)
                predictor._model = loaded._model
                predictor._loaded = loaded._loaded
                predictor.version = loaded.version
                predictor.r2 = loaded.r2
            except Exception as exc:
                logger.error("curator: predictor reload failed: %s", exc)

    r2_after = predictor.r2
    # Reload the corpus snapshot so the in-memory percentile cache reflects new rows.
    corpus.load(config.CACHE_DIR / "corpus.jsonl")

    if (
        r2_before is not None
        and r2_after is not None
        and (r2_before - r2_after) > config.CURATOR_R2_REGRESSION_THRESHOLD
    ):
        logger.warning(
            "curator: R² regressed %.4f → %.4f (>%.2f) — rolling back %d rows",
            r2_before, r2_after, config.CURATOR_R2_REGRESSION_THRESHOLD, len(new_row_indices),
        )
        if snapshot.exists():
            shutil.copy2(snapshot, pkl)
            try:
                loaded = EngagementPredictor.load(pkl)
                predictor._model = loaded._model
                predictor._loaded = loaded._loaded
                predictor.version = loaded.version
                predictor.r2 = loaded.r2
            except Exception as exc:
                logger.error("curator: rollback reload failed: %s", exc)
        excluded = _exclude_rows_in_corpus(new_row_indices)
        if snapshot.exists():
            try:
                snapshot.unlink()
            except OSError:
                pass
        return excluded

    if snapshot.exists():
        try:
            snapshot.unlink()
        except OSError:
            pass
    return []


def _invoke_fit_predictor(out_path: Path) -> dict[str, Any]:
    """Thin wrapper so the script-level fit_predictor function is importable
    here without making `scripts/` a package. We import lazily."""
    sys.path.insert(0, str(config.GX10_ROOT / "scripts"))
    try:
        from fit_predictor import fit_predictor as _fit  # type: ignore
    finally:
        # Clean the path so we don't leak it into other imports.
        try:
            sys.path.remove(str(config.GX10_ROOT / "scripts"))
        except ValueError:
            pass
    return _fit(
        corpus_path=config.CACHE_DIR / "corpus.jsonl",
        out_path=out_path,
        seed=config.CURATOR_REFIT_SEED,
        test_frac=config.CURATOR_REFIT_TEST_FRAC,
    )


def _exclude_rows_in_corpus(row_indices: list[int]) -> list[int]:
    """Set `excluded:true` on the given rows (0-based indices) in corpus.jsonl.
    Rewrites the file once; preserves all other rows untouched. Returns the
    list of indices actually marked (those that existed)."""
    path = config.CACHE_DIR / "corpus.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    marked: list[int] = []
    out: list[str] = []
    for i, line in enumerate(lines):
        if i in row_indices and line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                out.append(line)
                continue
            row["excluded"] = True
            row["excluded_reason"] = "r2_regression"
            out.append(json.dumps(row))
            marked.append(i)
        else:
            out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return marked


# ---------------------------------------------------------------------------
# Self-supervised query expansion (PRD §11.7 source 3).
# ---------------------------------------------------------------------------


async def _augment_query_pool(
    new_rows: list[dict[str, Any]],
    gemma: Any,
    transcribe_fn: Callable[[Path], str],
) -> None:
    """If at least N new rows AND at least one is top-quartile-ish (rate ≥ threshold),
    ask Gemma for 1-2 new queries based on top-quartile transcripts. Append to
    cache/curator_query_pool.jsonl (FIFO cap)."""
    if len(new_rows) < config.CURATOR_QUERY_EXPANSION_MIN_ROWS:
        return
    top = [r for r in new_rows if (r.get("engagement_rate") or 0.0) >= config.CURATOR_QUERY_EXPANSION_MIN_RATE]
    if not top:
        return

    # We don't actually re-download mp4s here — the transcripts of the top rows
    # were already captured in the row when /library/from-job style flows ran.
    # For corpus rows from the curator, the mp4 was deleted post-feature-extract
    # so we summarize from yt-dlp metadata (title + uploader) instead. PRD §11.7
    # source 3 says "transcripts" but title/uploader is a strict subset that
    # avoids re-downloading; revisit if query quality suffers.
    summaries: list[str] = []
    for r in top[:3]:
        title = (r.get("title") or "").strip() if isinstance(r.get("title"), str) else ""
        uploader = (r.get("uploader") or "").strip() if isinstance(r.get("uploader"), str) else ""
        summaries.append(f"- {title} ({uploader}, rate={r.get('engagement_rate'):.3f})")
    prompt = (
        "These YouTube Shorts are over-performing relative to their channel size. "
        "Generate 2 short YouTube search queries (under 8 words each) for finding "
        "more clips like these. One per line, no numbering or commentary.\n\n"
        + "\n".join(summaries)
        + "\n\nSearch queries:"
    )
    try:
        text = await asyncio.to_thread(gemma.generate, prompt, 80)
    except Exception as exc:
        logger.error("curator: gemma query-expansion failed: %s", exc)
        return

    from .curator_gap import _parse_queries
    queries = _parse_queries(text, k=2)
    if not queries:
        return

    _append_query_pool(queries, source_video_ids=[r.get("video_id") for r in top])


def _append_query_pool(queries: list[str], source_video_ids: list[str]) -> None:
    """Append new queries to cache/curator_query_pool.jsonl, then truncate to
    the most-recent CURATOR_QUERY_POOL_MAX_SIZE entries (FIFO)."""
    path = config.CURATOR_QUERY_POOL_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[str] = []
    if path.exists():
        existing = path.read_text(encoding="utf-8").splitlines()
    rows = list(existing)
    for q in queries:
        rows.append(json.dumps({
            "query": q,
            "added_at": _now_iso(),
            "source_video_ids": [v for v in source_video_ids if isinstance(v, str)],
        }))
    if len(rows) > config.CURATOR_QUERY_POOL_MAX_SIZE:
        rows = rows[-config.CURATOR_QUERY_POOL_MAX_SIZE:]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Trending iteration (PRD §11.8) — same yt-dlp+TRIBE pipeline as corpus,
# different terminal step: writes LibraryEntry-shaped JSON to
# cache/trending/<yyyy-mm-dd>/<video_id>.json. R-05's /inspiration endpoint
# reads from this pool to rank against creator centroids.
# ---------------------------------------------------------------------------


async def _run_trending_iteration(
    iter_count: int,
    active_streams_fn: Callable[[], int],
) -> None:
    from . import curator_gap
    from .corpus import corpus
    from .gemma import gemma_service
    from .pooling import frames_to_array, pool_tribe_output, roi_mean_vector
    from .predictor import predictor
    from .text_embed import embed_text
    from .transcribe import transcribe
    from .tribe import tribe_service

    iter_log: dict[str, Any] = {
        "ts": _now_iso(),
        "iter": iter_count,
        "type": "trending",
        "queries": [],
        "n_added": 0,
        "n_pruned": 0,
    }

    # Cleanup expired date partitions (PRD §11.8 7-day TTL).
    iter_log["n_pruned"] = _prune_old_trending_dirs()

    queries = curator_gap.pick_queries(
        iter_type="trending",
        corpus=corpus,
        predictor=predictor,
        gemma=gemma_service,
        query_pool_path=config.CURATOR_QUERY_POOL_FILE,
    )
    iter_log["queries"] = queries
    logger.info("curator: iter=%d trending queries=%s", iter_count, queries)

    # Dedupe across the entire trending pool — re-running the same trending
    # search next iteration shouldn't re-process clips already in the pool.
    existing_ids = _read_trending_video_ids()

    candidates: list[dict[str, Any]] = []
    for q in queries:
        try:
            metas = await _ytsearch_metadata(q)
        except Exception as exc:
            logger.error("curator: trending ytsearch failed for %r: %s", q, exc)
            continue
        for meta in _filter_search_results(metas, existing_ids):
            if meta["id"] in {c["id"] for c in candidates}:
                continue
            candidates.append(meta)
            if len(candidates) >= config.CURATOR_TRENDING_URLS_PER_ITERATION:
                break
        if len(candidates) >= config.CURATOR_TRENDING_URLS_PER_ITERATION:
            break

    today_dir = config.CURATOR_TRENDING_DIR / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_dir.mkdir(parents=True, exist_ok=True)

    n_added = 0
    with tempfile.TemporaryDirectory(prefix="cortex_trending_") as tmp:
        tmp_dir = Path(tmp)
        for meta in candidates:
            if active_streams_fn() > 0:
                logger.info("curator: iter=%d trending — yielding to active streams", iter_count)
                break
            try:
                entry = await _process_trending_candidate(
                    meta, tmp_dir, tribe_service,
                    frames_to_array, pool_tribe_output, roi_mean_vector,
                    transcribe, embed_text,
                )
            except Exception as exc:
                logger.error("curator: per-URL trending failed for %s: %s", meta.get("id"), exc)
                continue
            if entry is None:
                continue
            _write_trending_entry(today_dir, entry)
            n_added += 1

    iter_log["n_added"] = n_added
    _append_log_row(iter_log)


async def _process_trending_candidate(
    meta: dict[str, Any],
    tmp_dir: Path,
    tribe_service: Any,
    frames_to_array: Callable[..., Any],
    pool_tribe_output: Callable[..., Any],
    roi_mean_vector: Callable[..., Any],
    transcribe_fn: Callable[..., str],
    embed_fn: Callable[..., Any],
) -> dict[str, Any] | None:
    """Download → TRIBE (locked) → Whisper → nomic embed → trending dict."""
    url = meta.get("webpage_url") or meta.get("original_url") or f"https://youtube.com/shorts/{meta.get('id')}"
    video_path: Path | None = None
    try:
        video_path = await _ytdlp_download(url, tmp_dir)
        async with tribe_service.lock:
            result = await asyncio.to_thread(tribe_service.analyze_video, video_path)
        arr = frames_to_array(result["brain_frames"])
        pooled = pool_tribe_output(arr)
        rois = roi_mean_vector(arr)
        transcript = await asyncio.to_thread(transcribe_fn, video_path)
        text_emb = await asyncio.to_thread(embed_fn, transcript or "")
        duration_s = float(result.get("duration_s") or arr.shape[0])

        vid = str(meta.get("id"))
        return {
            "video_id": f"yt:{vid}",
            "uploaded_at": _now_iso(),
            "duration_s": duration_s,
            "tribe_pooled": np.asarray(pooled, dtype=np.float32).tolist(),
            "roi_means": np.asarray(rois, dtype=np.float32).tolist(),
            "transcript": transcript or "",
            "text_embedding": np.asarray(text_emb, dtype=np.float32).tolist(),
            "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            # Trending-specific fields R-05's /inspiration response needs.
            "source_url": meta.get("webpage_url"),
            "creator_handle": meta.get("uploader") or meta.get("channel"),
            "view_count": int(meta.get("view_count") or 0),
            "engagement_rate": _compute_engagement_rate(meta),
        }
    finally:
        if video_path is not None and video_path.exists():
            try:
                video_path.unlink()
            except OSError:
                pass


def _compute_engagement_rate(meta: dict[str, Any]) -> float:
    """(likes + comments) / views — standard creator-side engagement formula."""
    views = float(meta.get("view_count") or 0)
    if views <= 0:
        return 0.0
    likes = float(meta.get("like_count") or 0)
    comments = float(meta.get("comment_count") or 0)
    return (likes + comments) / views


def _read_trending_video_ids() -> set[str]:
    """Walk all date subdirs of CURATOR_TRENDING_DIR, return all seen video_ids
    in `yt:<id>` format (matching _filter_search_results' dedupe key)."""
    out: set[str] = set()
    if not config.CURATOR_TRENDING_DIR.exists():
        return out
    for date_dir in config.CURATOR_TRENDING_DIR.iterdir():
        if not date_dir.is_dir():
            continue
        for json_path in date_dir.glob("*.json"):
            out.add(f"yt:{json_path.stem}")
    return out


def _prune_old_trending_dirs() -> int:
    """Delete cache/trending/<date>/ folders older than CURATOR_TRENDING_TTL_DAYS.
    Returns count of pruned date partitions. Malformed dir names are skipped
    (not deleted — better safe than sorry on filesystem ops)."""
    if not config.CURATOR_TRENDING_DIR.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.CURATOR_TRENDING_TTL_DAYS)
    pruned = 0
    for date_dir in config.CURATOR_TRENDING_DIR.iterdir():
        if not date_dir.is_dir():
            continue
        try:
            d = datetime.strptime(date_dir.name, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if d < cutoff:
            shutil.rmtree(date_dir, ignore_errors=True)
            pruned += 1
            logger.info("curator: pruned old trending dir %s", date_dir.name)
    return pruned


def _write_trending_entry(date_dir: Path, entry: dict[str, Any]) -> None:
    """Write entry to <date_dir>/<video_id_without_yt_prefix>.json.

    Strips the `yt:` prefix from the filename so paths stay POSIX-friendly;
    the in-file `video_id` field keeps the prefix for downstream reads."""
    vid = entry["video_id"]
    safe = vid.split(":", 1)[1] if ":" in vid else vid
    path = date_dir / f"{safe}.json"
    path.write_text(json.dumps(entry), encoding="utf-8")


def count_trending_entries() -> int:
    """Public helper — used by /curator/status to report trending_pool_size."""
    if not config.CURATOR_TRENDING_DIR.exists():
        return 0
    return sum(1 for _ in config.CURATOR_TRENDING_DIR.glob("*/*.json"))


# ---------------------------------------------------------------------------
# Iteration log.
# ---------------------------------------------------------------------------


def _append_log_row(row: dict[str, Any]) -> None:
    path = config.CURATOR_LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


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
