# Cortex brain — FastAPI app on the GX10.
# Implements PRD §3 (architecture) + §9 (API contracts) — all 7 endpoints.
# P0-A: stub responses; real TRIBE/Gemma/ffmpeg wiring arrives in P1/P2.
# CORTEX_STUB_TRIBE=1 + CORTEX_STUB_GEMMA=1 lets this run on a laptop without the model stack.
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
from sse_starlette.sse import EventSourceResponse

from . import config, models, streaming
from .cache import hero_cache
from .gemma import gemma_service
from .tribe import tribe_service

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    hero_cache.load_heroes()
    tribe_service.load()
    gemma_service.load()
    yield


app = FastAPI(title="Cortex Brain", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_STARTED_AT = time.time()
_JOBS: dict[str, dict[str, Any]] = {}


@app.get("/health", response_model=models.HealthResponse)
async def health() -> models.HealthResponse:
    return models.HealthResponse(
        status="ok" if (tribe_service.loaded and gemma_service.loaded) else "degraded",
        tribe_loaded=tribe_service.loaded,
        gemma_loaded=gemma_service.loaded,
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

        # Run inference (stub returns synthetic frames).
        if mode == "text":
            result = tribe_service.analyze_text(job["input"]["text"])
        elif mode == "audio":
            result = tribe_service.analyze_audio(Path(job["input"]["path"]))
        else:
            path = Path(job["input"].get("path", ""))
            result = tribe_service.analyze_video(path)

        if mode in ("audio", "video"):
            yield streaming.transcript(result.get("transcript", []))

        for frame in result["brain_frames"]:
            yield streaming.brain_frame(t=frame["t"], activation=frame["activation"])
            await asyncio.sleep(0.03)

        yield streaming.cold_zones(result["cold_zones"])
        yield streaming.suggestions([])
        yield streaming.complete(
            {
                "mode": mode,
                "duration_s": result.get("duration_s", 0),
                "engagement_curves": result.get("engagement_curves", {}),
            }
        )

    return EventSourceResponse(gen())


@app.post("/auto-improve", response_model=models.JobAccepted)
async def auto_improve(req: models.AutoImproveRequest) -> models.JobAccepted:
    job_id = str(uuid.uuid4())
    _JOBS[job_id] = {"mode": "video", "auto_improve": True, "clip_id": req.clip_id, "version": req.version}
    return models.JobAccepted(job_id=job_id, mode="video", estimated_ms=55_000)


@app.get("/stream-improve/{job_id}")
async def stream_improve(job_id: str) -> EventSourceResponse:
    job = _JOBS.get(job_id)
    if not job or not job.get("auto_improve"):
        raise HTTPException(status_code=404, detail="unknown auto-improve job")

    async def gen():
        async for tok in gemma_service.stream_completion(system="", user=""):
            yield streaming.reasoning(tok)
        cut = {"operation": "cut", "params": {"start_t": 14.0, "end_t": 21.0}}
        yield streaming.cutting(cut)
        await asyncio.sleep(0.5)
        yield streaming.cut_applied(v2_url="/cache/auto_improve/khan/v2.mp4")
        yield streaming.reanalyzing()
        # Replay v2 frames (stub).
        result = tribe_service.analyze_video(Path("stub.mp4"))
        for frame in result["brain_frames"]:
            yield streaming.brain_frame(t=frame["t"], activation=frame["activation"])
            await asyncio.sleep(0.02)
        yield streaming.complete({
            "v2_engagement": result["engagement_curves"],
            "v2_cold_zones": result["cold_zones"],
            "v2_suggestions": [],
        })

    return EventSourceResponse(gen())


@app.post("/apply-suggestion", response_model=models.ApplySuggestionResponse)
async def apply_suggestion(req: models.ApplySuggestionRequest) -> models.ApplySuggestionResponse:
    if req.action == "reject":
        return models.ApplySuggestionResponse()
    # Stub: real text rewriter + new analyze job lands in P1-06/07.
    new_job_id = str(uuid.uuid4())
    _JOBS[new_job_id] = {"mode": "text", "input": {"text": "(rewritten stub)"}}
    return models.ApplySuggestionResponse(new_text="(rewritten stub)", job_id=new_job_id)
