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
