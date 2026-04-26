// Frontend DTOs mirroring backend Pydantic models.
// PRD §9 (API contracts) — keep in sync with cortex/gx10/brain/models.py.
// PH-D / P0-B scaffold only — fields filled in as endpoints land.
// Backend is authoritative; frontend follows.
// See docs/PRD.md §9.

export type Mode = 'text' | 'audio' | 'video';

export type AnalysisStatus =
  | 'idle'
  | 'submitting'
  | 'streaming'
  | 'complete'
  | 'error';

export interface ColdZone {
  start: number;
  end: number;
  region: string;
  depth?: number;
}

export interface EditSuggestion {
  id: string;
  cold_zone: ColdZone;
  rationale: string;
  // text-mode: rewritten sentence; audio/video: cut params
  rewrite?: string;
  cut?: { start_t: number; end_t: number };
}

export interface BrainFrame {
  t: number;
  activation: number[];
}

export interface TranscriptWord {
  text: string;
  start: number;
  end: number;
}

// Per-track engagement: track name → per-second score in [-1.5, 1.5] roughly.
// Common keys for video: "visual", "auditory", "language". Audio omits "visual".
export type EngagementCurves = Record<string, number[]>;

// §11.1 — engagement prediction.
export interface PredictEngagementResponse {
  predicted_rate: number;
  percentile: number;
  interpretation: string;
  corpus_size: number;
  predictor_version: string;
  followers_used: number;
  duration_s: number;
  n_cold_zones: number;
}

// §11.6 — creator library + originality search.
export type RoiName = 'visual' | 'auditory' | 'language';

export interface RoiBreakdown {
  visual: number;
  auditory: number;
  language: number;
}

export interface SimilarityMatch {
  video_id: string;
  score: number;
  thumbnail_url: string | null;
  uploaded_at: string;
  duration_s: number;
  dominant_roi: RoiName;
  roi_breakdown: RoiBreakdown;
  text_similarity: number;
}

export interface SimilarityResponse {
  matches: SimilarityMatch[];
  library_size: number;
  creator_id: string;
  weighting?: { brain: number; text: number };
  message?: string;
}

export interface LibraryEntryMeta {
  video_id: string;
  uploaded_at: string;
  duration_s: number;
  thumbnail_url: string | null;
}

export interface LibraryListResponse {
  creator_id: string;
  size: number;
  entries: LibraryEntryMeta[];
}

export interface LibraryUploadResponse {
  library_entry_id: string;
  library_size: number;
}
