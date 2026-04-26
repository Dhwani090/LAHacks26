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


class BrainFrame(BaseModel):
    t: float
    activation: list[float]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "loading"]
    tribe_loaded: bool
    gemma_loaded: bool
    predictor_loaded: bool
    corpus_size: int
    cache_size: int
    gx10_uptime_s: float


class PredictEngagementRequest(BaseModel):
    job_id: str
    followers: int = Field(default=0, ge=0)


class PredictEngagementResponse(BaseModel):
    predicted_rate: float
    percentile: int
    interpretation: str
    corpus_size: int
    predictor_version: str
    followers_used: int
    duration_s: float
    n_cold_zones: int


class ApplySuggestionRequest(BaseModel):
    clip_id: str
    suggestion_id: str
    action: Literal["apply", "reject"]


class ApplySuggestionResponse(BaseModel):
    new_text: str | None = None
    job_id: str | None = None


# §11.6 — creator library + originality search.
class SimilarityRequest(BaseModel):
    job_id: str
    creator_id: str = Field(..., min_length=1, max_length=64)


class RoiBreakdown(BaseModel):
    visual: float
    auditory: float
    language: float


class SimilarityMatch(BaseModel):
    video_id: str
    score: float
    thumbnail_url: str | None = None
    uploaded_at: str
    duration_s: float
    dominant_roi: Literal["visual", "auditory", "language"]
    roi_breakdown: RoiBreakdown
    text_similarity: float


class SimilarityResponse(BaseModel):
    matches: list[SimilarityMatch]
    library_size: int
    creator_id: str
    weighting: dict[str, float] | None = None
    message: str | None = None


class LibraryEntryMeta(BaseModel):
    video_id: str
    uploaded_at: str
    duration_s: float
    thumbnail_url: str | None = None


class LibraryListResponse(BaseModel):
    creator_id: str
    size: int
    entries: list[LibraryEntryMeta]


class LibraryUploadResponse(BaseModel):
    library_entry_id: str
    library_size: int


class LibraryFromJobRequest(BaseModel):
    job_id: str
    creator_id: str = Field(..., min_length=1, max_length=64)
    # Optional override; defaults to a name derived from the original upload filename.
    video_id: str | None = Field(default=None, max_length=128)
