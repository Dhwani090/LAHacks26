// AppState — global UI state (mode, analysis status, brain frame buffer).
// PRD §7 (frontend modules) — Zustand store referenced by all surfaces.
// Backend integration arrives with P1 SSE wiring; this is shell scaffolding.
// Components import { useAppState } and select narrow slices.
// See docs/PRD.md §7.
'use client';

import { create } from 'zustand';
import type {
  AnalysisStatus,
  BrainFrame,
  ColdZone,
  EditSuggestion,
  Mode,
} from '../lib/types';

interface AppStateData {
  mode: Mode;
  status: AnalysisStatus;
  jobId: string | null;
  brainFrames: BrainFrame[];
  coldZones: ColdZone[];
  suggestions: EditSuggestion[];
  errorMessage: string | null;
}

interface AppStateActions {
  setMode: (mode: Mode) => void;
  setStatus: (status: AnalysisStatus) => void;
  setJobId: (jobId: string | null) => void;
  appendBrainFrame: (frame: BrainFrame) => void;
  setColdZones: (zones: ColdZone[]) => void;
  setSuggestions: (suggestions: EditSuggestion[]) => void;
  setError: (msg: string | null) => void;
  resetAnalysis: () => void;
}

const initialAnalysis = {
  status: 'idle' as AnalysisStatus,
  jobId: null,
  brainFrames: [],
  coldZones: [],
  suggestions: [],
  errorMessage: null,
};

export const useAppState = create<AppStateData & AppStateActions>((set) => ({
  mode: 'text',
  ...initialAnalysis,

  setMode: (mode) => set({ mode, ...initialAnalysis }),
  setStatus: (status) => set({ status }),
  setJobId: (jobId) => set({ jobId }),
  appendBrainFrame: (frame) =>
    set((s) => ({ brainFrames: [...s.brainFrames, frame] })),
  setColdZones: (coldZones) => set({ coldZones }),
  setSuggestions: (suggestions) => set({ suggestions }),
  setError: (errorMessage) =>
    set({ errorMessage, status: errorMessage ? 'error' : 'idle' }),
  resetAnalysis: () => set({ ...initialAnalysis }),
}));
