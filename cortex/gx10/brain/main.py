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

from . import config, models, streaming
from .cache import hero_cache
from .corpus import corpus
from .gemma import gemma_service
from .pooling import frames_to_array, pool_tribe_output
from .predictor import load_default_predictor, predictor
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
    yield


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
        _JOBS[job_id] = {"mode": "video", "input": {"path": str(tmp_path)}}
    else:
        _JOBS[job_id] = {"mode": "video", "input": {"cloudinary_public_id": cloudinary_public_id}}
    return models.JobAccepted(job_id=job_id, mode="video", estimated_ms=45_000)


@app.get("/stream/{job_id}")
async def stream(job_id: str) -> EventSourceResponse:
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="unknown job_id")

    async def gen():
        mode = job["mode"]
        budgets = {"text": config.TEXT_BUDGET_S, "audio": config.AUDIO_BUDGET_S, "video": config.VIDEO_BUDGET_S}
        yield streaming.started(mode=mode, estimated_ms=int(budgets[mode] * 1000))

        if mode == "text":
            result = tribe_service.analyze_text(job["input"]["text"])
        elif mode == "audio":
            result = tribe_service.analyze_audio(Path(job["input"]["path"]))
        else:
            path = Path(job["input"].get("path") or "stub.mp4")
            result = tribe_service.analyze_video(path)

        if mode in ("audio", "video"):
            yield streaming.transcript(result.get("transcript", []))

        for frame in result["brain_frames"]:
            yield streaming.brain_frame(t=frame["t"], activation=frame["activation"])
            await asyncio.sleep(0.03)

        yield streaming.cold_zones(result["cold_zones"])
        yield streaming.suggestions([])

        # For video jobs, cache pooled TRIBE features so /predict-engagement can
        # look them up by job_id without re-running inference.
        if mode == "video":
            try:
                arr = frames_to_array(result["brain_frames"])
                job["pooled_features"] = pool_tribe_output(arr).tolist()
                job["duration_s"] = float(result.get("duration_s") or arr.shape[0])
                job["n_cold_zones"] = int(len(result.get("cold_zones") or []))
            except Exception as exc:
                logger.error("pooling failed for job %s: %s", job_id, exc)

        yield streaming.complete(
            {
                "mode": mode,
                "duration_s": result.get("duration_s", 0),
                "engagement_curves": result.get("engagement_curves", {}),
            }
        )

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
