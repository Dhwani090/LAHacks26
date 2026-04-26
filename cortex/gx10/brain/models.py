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
    # Candidate-set filters (PRD §11.6 — creator-tunable similarity search).
    # Default last_n=50 keeps comparison anchored to the creator's recent
    # voice; older work is often a different style and dilutes the signal.
    # last_n     = compare only against the N most recently uploaded entries.
    #              None or 0 means "no cap" (use whole library, subject to
    #              since_days if also set).
    # since_days = only consider entries uploaded within the last N days.
    #              None means "no time filter".
    # If both are set, since_days filters first, then last_n caps.
    last_n: int | None = Field(default=50, ge=0, le=100_000)
    since_days: int | None = Field(default=None, ge=1, le=3650)


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
    # candidate_size = number of entries that survived the user's filter
    # (last_n / since_days) and were actually ranked. Frontend uses this in
    # the "ranked vs. N past clips" caption so the count reflects the window,
    # not the full library.
    candidate_size: int = 0
    creator_id: str
    weighting: dict[str, float] | None = None
    # Echo of the filter the request used, so the UI can keep the dropdown
    # state honest after the round-trip (e.g. clamp to library size).
    filter: dict[str, int | None] | None = None
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


class CuratorStatusResponse(BaseModel):
    """Status of the NemoClaw curator (PRD §11.7).

    Forward-compatible shape — R-01 fills in `running` / iter counters / kill-switch
    state; R-02/R-03/R-04 populate `last_r2`, `corpus_size`, `trending_pool_size`."""
    running: bool
    enabled: bool  # cache/curator.enabled present
    kill_switch: bool  # cache/curator.disabled present (vetoes enabled)
    paused_for_jobs: bool
    iter_count: int
    last_iter_at: str | None = None
    last_iter_type: Literal["corpus", "trending"] | None = None
    corpus_size: int = 0
    trending_pool_size: int = 0
    last_r2: float | None = None
