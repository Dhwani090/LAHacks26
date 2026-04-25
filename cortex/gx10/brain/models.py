# Pydantic DTOs — wire format between Cortex frontend and backend.
# PRD §9 (API contracts) — keep in sync with cortex/web/src/app/lib/types.ts.
# Names mirror frontend; field types are authoritative here.
# See docs/PRD.md §9.

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


Mode = Literal["text", "audio", "video"]


class AnalyzeTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class JobAccepted(BaseModel):
    job_id: str
    mode: Mode
    estimated_ms: int


class TranscriptWord(BaseModel):
    text: str
    start: float
    end: float


class ColdZone(BaseModel):
    start: float
    end: float
    region: str
    depth: float | None = None


class EditSuggestion(BaseModel):
    id: str
    cold_zone: ColdZone
    rationale: str
    rewrite: str | None = None
    cut: dict | None = None  # {"start_t": float, "end_t": float}


class BrainFrame(BaseModel):
    t: float
    activation: list[float]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "loading"]
    tribe_loaded: bool
    gemma_loaded: bool
    cache_size: int
    gx10_uptime_s: float


class AutoImproveRequest(BaseModel):
    clip_id: str
    version: int


class ApplySuggestionRequest(BaseModel):
    clip_id: str
    suggestion_id: str
    action: Literal["apply", "reject"]


class ApplySuggestionResponse(BaseModel):
    new_text: str | None = None
    job_id: str | None = None
