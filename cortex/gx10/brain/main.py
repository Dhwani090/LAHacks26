# Cortex brain — FastAPI app on the GX10.
# Implements PRD §3 (architecture) + §9 (API contracts).
# Three analysis modes (text/audio/video) over SSE; auto-editing was removed —
# next iteration of "improve" will be a different surface.
# See docs/PRD.md §9.

from __future__ import annotations
import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from . import config, curator as curator_mod, models, streaming
from .cache import hero_cache
from .corpus import corpus
from .gemma import gemma_service
from .library import LibraryEntry, filter_candidates, library_registry, now_iso, rank_similar
from .pooling import frames_to_array, pool_tribe_output, roi_mean_vector
from .predictor import load_default_predictor, predictor
from .text_embed import embed_text
from .transcribe import transcribe
from .tribe import tribe_service

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    hero_cache.load_heroes()
    tribe_service.load()
    gemma_service.load()
    corpus.load(config.CACHE_DIR / "corpus.jsonl")
    load_default_predictor()
    # NemoClaw curator (PRD §11.7) — off unless cache/curator.enabled exists.
    # Spawn unconditionally so a creator can flip the gate file at runtime; the
    # loop stays idle while the file is absent.
    curator_task: asyncio.Task[None] | None = None
    if not curator_mod.is_stub():
        curator_task = asyncio.create_task(
            curator_mod.curator_loop(active_streams_fn=lambda: _active_streams)
        )
    try:
        yield
    finally:
        if curator_task is not None:
            curator_task.cancel()
            try:
                await curator_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Cortex Brain", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve any pre-rendered hero assets to the frontend.
config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/cache", StaticFiles(directory=str(config.CACHE_DIR)), name="cache")

_STARTED_AT = time.time()
_JOBS: dict[str, dict[str, Any]] = {}
# Curator priority gate (PRD §11.7) — incremented at top of /stream/{job_id}
# and decremented in try/finally so the loop yields the box to live inference.
_active_streams: int = 0


@app.get("/health", response_model=models.HealthResponse)
async def health() -> models.HealthResponse:
    all_loaded = tribe_service.loaded and gemma_service.loaded and predictor.loaded
    return models.HealthResponse(
        status="ok" if all_loaded else "degraded",
        tribe_loaded=tribe_service.loaded,
        gemma_loaded=gemma_service.loaded,
        predictor_loaded=predictor.loaded,
        corpus_size=corpus.size(),
        cache_size=hero_cache.size(),
        gx10_uptime_s=time.time() - _STARTED_AT,
    )


@app.post("/analyze/text", response_model=models.JobAccepted)
async def analyze_text(req: models.AnalyzeTextRequest) -> models.JobAccepted:
    job_id = str(uuid.uuid4())
    _JOBS[job_id] = {"mode": "text", "input": {"text": req.text}}
    return models.JobAccepted(job_id=job_id, mode="text", estimated_ms=10_000)


@app.post("/analyze/audio", response_model=models.JobAccepted)
async def analyze_audio(file: UploadFile = File(...)) -> models.JobAccepted:
    job_id = str(uuid.uuid4())
    tmp_path = config.CACHE_DIR / "uploads" / f"{job_id}_{file.filename}"
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    with tmp_path.open("wb") as f:
        f.write(await file.read())
    _JOBS[job_id] = {"mode": "audio", "input": {"path": str(tmp_path)}}
    return models.JobAccepted(job_id=job_id, mode="audio", estimated_ms=18_000)


@app.post("/analyze/video", response_model=models.JobAccepted)
async def analyze_video(
    file: UploadFile | None = File(None),
    cloudinary_public_id: str | None = Form(None),
) -> models.JobAccepted:
    if file is None and not cloudinary_public_id:
        raise HTTPException(status_code=400, detail="file or cloudinary_public_id required")
    job_id = str(uuid.uuid4())
    if file is not None:
        tmp_path = config.CACHE_DIR / "uploads" / f"{job_id}_{file.filename}"
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        with tmp_path.open("wb") as f:
            f.write(await file.read())
        _JOBS[job_id] = {
            "mode": "video",
            "input": {"path": str(tmp_path)},
            "source_name": file.filename or "draft.mp4",
        }
    else:
        _JOBS[job_id] = {
            "mode": "video",
            "input": {"cloudinary_public_id": cloudinary_public_id},
            "source_name": cloudinary_public_id or "draft",
        }
    return models.JobAccepted(job_id=job_id, mode="video", estimated_ms=45_000)


@app.get("/heroes")
async def heroes() -> dict[str, list[dict[str, Any]]]:
    """List the hero clips available for one-click demo replay."""
    out: list[dict[str, Any]] = []
    for mode in ("video", "audio", "text"):
        # `_store` keys look like `hero_video:slug` — see HeroCache.load_heroes.
        prefix = f"hero_{mode}:"
        for key in hero_cache._store:
            if key.startswith(prefix):
                slug = key[len(prefix):]
                out.append({"mode": mode, "slug": slug})
    return {"heroes": out}


@app.post("/analyze/hero", response_model=models.JobAccepted)
async def analyze_hero(slug: str = Form(...), mode: str = Form("video")) -> models.JobAccepted:
    """Demo-friendly fast path. If the hero JSON is cached, /stream replays it
    instantly; otherwise we fall through to stub TRIBE on a synthetic input so
    the demo never blocks on an empty cache."""
    if mode not in ("video", "audio", "text"):
        raise HTTPException(status_code=400, detail="mode must be video|audio|text")
    job_id = str(uuid.uuid4())
    cached = hero_cache.get_hero(mode, slug)
    estimated = 1_500 if cached is not None else {
        "text": config.TEXT_BUDGET_S,
        "audio": config.AUDIO_BUDGET_S,
        "video": config.VIDEO_BUDGET_S,
    }[mode] * 1000
    _JOBS[job_id] = {
        "mode": mode,
        "input": {"hero_slug": slug},
        "source_name": f"hero_{slug}",
        "hero_payload": cached,
    }
    return models.JobAccepted(job_id=job_id, mode=mode, estimated_ms=int(estimated))


@app.get("/stream/{job_id}")
async def stream(job_id: str) -> EventSourceResponse:
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="unknown job_id")

    async def gen():
        global _active_streams
        # Curator priority gate — keep this counter accurate even on early exit.
        _active_streams += 1
        try:
            mode = job["mode"]
            budgets = {"text": config.TEXT_BUDGET_S, "audio": config.AUDIO_BUDGET_S, "video": config.VIDEO_BUDGET_S}
            yield streaming.started(mode=mode, estimated_ms=int(budgets[mode] * 1000))

            # Hero replay: if the job carries a cached hero payload, surface it
            # directly. Falls through to live inference when the cache miss path
            # populates `hero_payload = None`.
            hero_payload = job.get("hero_payload")
            if hero_payload is not None:
                result = hero_payload
            elif mode == "text":
                result = tribe_service.analyze_text(job["input"]["text"])
            elif mode == "audio":
                audio_path = job["input"].get("path") or "stub.wav"
                result = tribe_service.analyze_audio(Path(audio_path))
            else:
                path = Path(job["input"].get("path") or job["input"].get("hero_slug") or "stub.mp4")
                result = tribe_service.analyze_video(path)

            if mode in ("audio", "video"):
                yield streaming.transcript(result.get("transcript", []))

            for frame in result["brain_frames"]:
                yield streaming.brain_frame(t=frame["t"], activation=frame["activation"])
                await asyncio.sleep(0.03)

            yield streaming.cold_zones(result["cold_zones"])
            yield streaming.suggestions([])

            # For video jobs, cache pooled TRIBE features + ROI means + transcript
            # embedding so /predict-engagement and /similarity can look them up by
            # job_id without re-running inference.
            if mode == "video":
                try:
                    arr = frames_to_array(result["brain_frames"])
                    job["pooled_features"] = pool_tribe_output(arr).tolist()
                    job["roi_means"] = roi_mean_vector(arr).tolist()
                    job["duration_s"] = float(result.get("duration_s") or arr.shape[0])
                    job["n_cold_zones"] = int(len(result.get("cold_zones") or []))
                    transcript_words = result.get("transcript") or []
                    transcript_text = " ".join(
                        w.get("text", "") if isinstance(w, dict) else str(w)
                        for w in transcript_words
                    ).strip()
                    job["transcript_text"] = transcript_text
                    if transcript_text:
                        job["text_embedding"] = embed_text(transcript_text).tolist()
                except Exception as exc:
                    logger.error("pooling failed for job %s: %s", job_id, exc)

            yield streaming.complete(
                {
                    "mode": mode,
                    "duration_s": result.get("duration_s", 0),
                    "engagement_curves": result.get("engagement_curves", {}),
                }
            )
        finally:
            _active_streams = max(0, _active_streams - 1)

    return EventSourceResponse(gen())


@app.post("/apply-suggestion", response_model=models.ApplySuggestionResponse)
async def apply_suggestion(req: models.ApplySuggestionRequest) -> models.ApplySuggestionResponse:
    if req.action == "reject":
        return models.ApplySuggestionResponse()
    new_job_id = str(uuid.uuid4())
    _JOBS[new_job_id] = {"mode": "text", "input": {"text": "(rewritten stub)"}}
    return models.ApplySuggestionResponse(new_text="(rewritten stub)", job_id=new_job_id)


def _interpret(percentile: int) -> str:
    if percentile >= 75:
        return "top 25% — this is hot for your audience size"
    if percentile >= 50:
        return "above median — solid for your account"
    if percentile >= 25:
        return "below median — worth iterating before posting"
    return "bottom quartile — the brain features look weak vs. comparable videos"


@app.post("/predict-engagement", response_model=models.PredictEngagementResponse)
async def predict_engagement(req: models.PredictEngagementRequest) -> models.PredictEngagementResponse:
    import numpy as np
    if not predictor.loaded:
        raise HTTPException(status_code=503, detail="predictor not loaded")
    job = _JOBS.get(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="unknown job_id")
    if job.get("mode") != "video":
        raise HTTPException(status_code=400, detail="predict-engagement requires a video job")
    pooled = job.get("pooled_features")
    if not pooled:
        raise HTTPException(status_code=409, detail="job has no pooled features yet — wait for /stream complete")

    followers = req.followers if req.followers > 0 else corpus.median_followers()
    duration_s = float(job.get("duration_s") or 30.0)
    n_cold_zones = int(job.get("n_cold_zones") or 0)

    out = predictor.predict(
        features=np.asarray(pooled, dtype=np.float32),
        followers=followers,
        duration_s=duration_s,
        n_cold_zones=n_cold_zones,
    )
    pct = corpus.percentile(out["predicted_rate"])
    return models.PredictEngagementResponse(
        predicted_rate=out["predicted_rate"],
        percentile=pct,
        interpretation=_interpret(pct),
        corpus_size=corpus.size(),
        predictor_version=predictor.version,
        followers_used=followers,
        duration_s=duration_s,
        n_cold_zones=n_cold_zones,
    )


# §11.6 — creator library + originality search.

@app.post("/library/upload", response_model=models.LibraryUploadResponse)
async def library_upload(
    creator_id: str = Form(...),
    file: UploadFile = File(...),
) -> models.LibraryUploadResponse:
    """Run TRIBE + Whisper + nomic-embed on the uploaded clip, persist only the
    features/embedding/transcript per creator, then delete the source mp4.

    PRD §11.6: the originality library is brain-features-only — we do not store
    the raw video. The library is also append-only: same `video_id` (Path stem)
    overwrites the existing entry rather than duplicating.
    """
    if not creator_id.strip():
        raise HTTPException(status_code=400, detail="creator_id required")
    safe_name = (file.filename or "upload.mp4").replace("/", "_")
    video_id = Path(safe_name).stem or uuid.uuid4().hex[:12]

    tmp_path = config.CACHE_DIR / "library_uploads" / creator_id / safe_name
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    with tmp_path.open("wb") as f:
        f.write(await file.read())

    try:
        result = tribe_service.analyze_video(tmp_path)
        arr = frames_to_array(result["brain_frames"])
        pooled = pool_tribe_output(arr)
        roi_means = roi_mean_vector(arr)
        transcript = transcribe(tmp_path)
        text_vec = embed_text(transcript)
        duration_s = float(result.get("duration_s") or arr.shape[0])
    except Exception as exc:
        logger.error("library upload pipeline failed for %s/%s: %s", creator_id, video_id, exc)
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"library pipeline failed: {exc}")
    finally:
        # Drop the mp4 — features + embeddings + transcript are all we keep.
        tmp_path.unlink(missing_ok=True)

    entry = LibraryEntry(
        video_id=video_id,
        uploaded_at=now_iso(),
        duration_s=duration_s,
        tribe_pooled=pooled,
        roi_means=roi_means,
        transcript=transcript,
        text_embedding=text_vec,
        thumbnail_url=None,
    )
    library_registry.save_entry(creator_id, entry)
    return models.LibraryUploadResponse(
        library_entry_id=video_id,
        library_size=library_registry.size(creator_id),
    )


@app.post("/library/from-job", response_model=models.LibraryUploadResponse)
async def library_from_job(req: models.LibraryFromJobRequest) -> models.LibraryUploadResponse:
    """Add a completed /analyze/video job to the creator's library without
    re-running TRIBE+Whisper. Reuses the pooled features, ROI means, and
    transcript embedding cached in _JOBS during /stream.

    Use case: user uploaded a draft to /predict, watched the brain pulse,
    decided it's worth posting, hits "Add to Library." We've already paid
    for inference — no reason to do it twice.
    """
    if not req.creator_id.strip():
        raise HTTPException(status_code=400, detail="creator_id required")
    job = _JOBS.get(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="unknown job_id")
    if job.get("mode") != "video":
        raise HTTPException(status_code=400, detail="library entries are video-only")

    pooled = job.get("pooled_features")
    roi_means = job.get("roi_means")
    if not pooled or not roi_means:
        raise HTTPException(status_code=409, detail="job has no pooled features yet — wait for /stream complete")

    source_name = job.get("source_name") or "draft.mp4"
    derived_id = Path(source_name).stem or req.job_id[:12]
    video_id = (req.video_id or derived_id).strip() or req.job_id[:12]

    transcript_text = job.get("transcript_text") or ""
    text_emb = job.get("text_embedding")
    if text_emb is not None:
        text_vec_arr = list(text_emb)
    else:
        text_vec_arr = embed_text(transcript_text).tolist()

    import numpy as np
    entry = LibraryEntry(
        video_id=video_id,
        uploaded_at=now_iso(),
        duration_s=float(job.get("duration_s") or 0.0),
        tribe_pooled=np.asarray(pooled, dtype=np.float32),
        roi_means=np.asarray(roi_means, dtype=np.float32),
        transcript=transcript_text,
        text_embedding=np.asarray(text_vec_arr, dtype=np.float32),
        thumbnail_url=None,
    )
    library_registry.save_entry(req.creator_id, entry)
    return models.LibraryUploadResponse(
        library_entry_id=video_id,
        library_size=library_registry.size(req.creator_id),
    )


@app.delete("/library/{creator_id}/{video_id}")
async def library_delete(creator_id: str, video_id: str) -> dict[str, Any]:
    """Remove one entry from the creator's library. Idempotent — calling it
    on an unknown video_id returns 404 so the UI can surface "already gone."
    Use case: creator added duplicates or a wrong file and wants to clean up
    before running similarity search."""
    if not creator_id.strip():
        raise HTTPException(status_code=400, detail="creator_id required")
    try:
        existed = library_registry.delete_entry(creator_id, video_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not existed:
        raise HTTPException(status_code=404, detail="library entry not found")
    return {
        "creator_id": creator_id,
        "video_id": video_id,
        "library_size": library_registry.size(creator_id),
    }


@app.get("/library/{creator_id}", response_model=models.LibraryListResponse)
async def library_list(creator_id: str) -> models.LibraryListResponse:
    entries = library_registry.load_creator_library(creator_id)
    return models.LibraryListResponse(
        creator_id=creator_id,
        size=len(entries),
        entries=[
            models.LibraryEntryMeta(
                video_id=e.video_id,
                uploaded_at=e.uploaded_at,
                duration_s=e.duration_s,
                thumbnail_url=e.thumbnail_url,
            )
            for e in entries
        ],
    )


@app.post("/similarity", response_model=models.SimilarityResponse)
async def similarity(req: models.SimilarityRequest) -> models.SimilarityResponse:
    import numpy as np

    job = _JOBS.get(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="unknown job_id")
    if job.get("mode") != "video":
        raise HTTPException(status_code=400, detail="similarity requires a video job")
    pooled = job.get("pooled_features")
    roi_means = job.get("roi_means")
    if not pooled or not roi_means:
        raise HTTPException(status_code=409, detail="job has no pooled features yet — wait for /stream complete")

    library = library_registry.load_creator_library(req.creator_id)
    if len(library) < config.SIMILARITY_MIN_LIBRARY_SIZE:
        return models.SimilarityResponse(
            matches=[],
            library_size=len(library),
            candidate_size=0,
            creator_id=req.creator_id,
            message=f"upload at least {config.SIMILARITY_MIN_LIBRARY_SIZE} past clips to enable originality search",
        )

    candidates = filter_candidates(
        library,
        last_n=req.last_n,
        since_days=req.since_days,
    )
    if len(candidates) < config.SIMILARITY_MIN_LIBRARY_SIZE:
        # Filter narrowed the set below the cold-start threshold — tell the
        # creator instead of returning a noisy ranking over 1-2 clips.
        return models.SimilarityResponse(
            matches=[],
            library_size=len(library),
            candidate_size=len(candidates),
            creator_id=req.creator_id,
            filter={"last_n": req.last_n, "since_days": req.since_days},
            message=f"only {len(candidates)} clip(s) match your filter — widen the window or upload more",
        )

    text_emb = job.get("text_embedding")
    draft_text = (
        np.asarray(text_emb, dtype=np.float32)
        if text_emb is not None
        else embed_text(job.get("transcript_text") or "")
    )

    matches = rank_similar(
        draft_brain=np.asarray(pooled, dtype=np.float32),
        draft_text=draft_text,
        draft_roi_means=np.asarray(roi_means, dtype=np.float32),
        library=candidates,
    )
    return models.SimilarityResponse(
        matches=[
            models.SimilarityMatch(
                video_id=m["video_id"],
                score=m["score"],
                thumbnail_url=m["thumbnail_url"],
                uploaded_at=m["uploaded_at"],
                duration_s=m["duration_s"],
                dominant_roi=m["dominant_roi"],
                roi_breakdown=models.RoiBreakdown(**m["roi_breakdown"]),
                text_similarity=m["text_similarity"],
            )
            for m in matches
        ],
        library_size=len(library),
        candidate_size=len(candidates),
        creator_id=req.creator_id,
        weighting={"brain": config.SIMILARITY_BRAIN_WEIGHT, "text": config.SIMILARITY_TEXT_WEIGHT},
        filter={"last_n": req.last_n, "since_days": req.since_days},
    )


@app.get("/curator/status", response_model=models.CuratorStatusResponse)
async def curator_status() -> models.CuratorStatusResponse:
    """NemoClaw curator state (PRD §11.7). R-01 fills running/iter fields;
    R-02/R-03/R-04 fill corpus_size, trending_pool_size, last_r2."""
    state = curator_mod.CURATOR_STATE
    return models.CuratorStatusResponse(
        running=state.running,
        enabled=config.CURATOR_ENABLED_FILE.exists(),
        kill_switch=config.CURATOR_DISABLED_FILE.exists(),
        paused_for_jobs=state.paused_for_jobs,
        iter_count=state.iter_count,
        last_iter_at=state.last_iter_at,
        last_iter_type=state.last_iter_type,  # type: ignore[arg-type]
        corpus_size=corpus.size(),
        trending_pool_size=0,  # populated by R-04
        last_r2=None,  # populated by R-03
    )
