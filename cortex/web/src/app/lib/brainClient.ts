// brainClient — typed wrapper for the GX10 backend.
// PRD §9 (API contracts) + §3 (HTTP/JSON + SSE over Tailscale).
// Native fetch + EventSource; NO axios per CLAUDE.md §3.
// Base URL from NEXT_PUBLIC_BRAIN_BASE_URL.
// See docs/PRD.md §9.

import type {
  BrainFrame,
  ColdZone,
  EditSuggestion,
  InspirationResponse,
  LibraryListResponse,
  LibraryUploadResponse,
  PredictEngagementResponse,
  SimilarityResponse,
  TranscriptWord,
} from './types';

const BASE = process.env.NEXT_PUBLIC_BRAIN_BASE_URL ?? '';

export interface JobAccepted {
  job_id: string;
  mode: 'text' | 'audio' | 'video';
  estimated_ms: number;
}

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'loading';
  tribe_loaded: boolean;
  gemma_loaded: boolean;
  predictor_loaded?: boolean;
  corpus_size?: number;
  cache_size: number;
  gx10_uptime_s: number;
}

class BrainClientError extends Error {}

function url(path: string): string {
  if (!BASE) {
    throw new BrainClientError(
      'NEXT_PUBLIC_BRAIN_BASE_URL not set. Copy cortex/web/.env.local.example to .env.local.',
    );
  }
  return `${BASE.replace(/\/$/, '')}${path}`;
}

async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url(path), {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) throw new BrainClientError(`${path} → ${res.status}`);
  return (await res.json()) as T;
}

async function postForm<T>(path: string, form: FormData, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url(path), { method: 'POST', body: form, signal });
  if (!res.ok) throw new BrainClientError(`${path} → ${res.status}`);
  return (await res.json()) as T;
}

export const brainClient = {
  async health(signal?: AbortSignal): Promise<HealthResponse> {
    const res = await fetch(url('/health'), { signal });
    if (!res.ok) throw new BrainClientError(`/health → ${res.status}`);
    return (await res.json()) as HealthResponse;
  },

  analyzeText(text: string, signal?: AbortSignal): Promise<JobAccepted> {
    return postJson<JobAccepted>('/analyze/text', { text }, signal);
  },

  analyzeAudio(file: File, signal?: AbortSignal): Promise<JobAccepted> {
    const fd = new FormData();
    fd.append('file', file);
    return postForm<JobAccepted>('/analyze/audio', fd, signal);
  },

  analyzeVideo(file: File, signal?: AbortSignal): Promise<JobAccepted> {
    const fd = new FormData();
    fd.append('file', file);
    return postForm<JobAccepted>('/analyze/video', fd, signal);
  },

  analyzeHero(
    slug: string,
    mode: 'text' | 'audio' | 'video' = 'video',
    signal?: AbortSignal,
  ): Promise<JobAccepted> {
    const fd = new FormData();
    fd.append('slug', slug);
    fd.append('mode', mode);
    return postForm<JobAccepted>('/analyze/hero', fd, signal);
  },

  async listHeroes(
    signal?: AbortSignal,
  ): Promise<{ heroes: { mode: 'text' | 'audio' | 'video'; slug: string }[] }> {
    const res = await fetch(url('/heroes'), { signal });
    if (!res.ok) throw new BrainClientError(`/heroes → ${res.status}`);
    return (await res.json()) as { heroes: { mode: 'text' | 'audio' | 'video'; slug: string }[] };
  },

  applySuggestion(
    clipId: string,
    suggestionId: string,
    action: 'apply' | 'reject',
    signal?: AbortSignal,
  ): Promise<{ new_text?: string; job_id?: string }> {
    return postJson('/apply-suggestion', { clip_id: clipId, suggestion_id: suggestionId, action }, signal);
  },

  predictEngagement(
    jobId: string,
    followers: number,
    signal?: AbortSignal,
  ): Promise<PredictEngagementResponse> {
    return postJson<PredictEngagementResponse>(
      '/predict-engagement',
      { job_id: jobId, followers },
      signal,
    );
  },

  // §11.6 — creator library + originality search.
  uploadLibraryEntry(
    creatorId: string,
    file: File,
    signal?: AbortSignal,
  ): Promise<LibraryUploadResponse> {
    const fd = new FormData();
    fd.append('creator_id', creatorId);
    fd.append('file', file);
    return postForm<LibraryUploadResponse>('/library/upload', fd, signal);
  },

  addJobToLibrary(
    jobId: string,
    creatorId: string,
    videoId?: string,
    signal?: AbortSignal,
  ): Promise<LibraryUploadResponse> {
    const body: { job_id: string; creator_id: string; video_id?: string } = {
      job_id: jobId,
      creator_id: creatorId,
    };
    if (videoId && videoId.trim()) body.video_id = videoId.trim();
    return postJson<LibraryUploadResponse>('/library/from-job', body, signal);
  },

  async getLibrary(creatorId: string, signal?: AbortSignal): Promise<LibraryListResponse> {
    const res = await fetch(url(`/library/${encodeURIComponent(creatorId)}`), { signal });
    if (!res.ok) throw new BrainClientError(`/library/${creatorId} → ${res.status}`);
    return (await res.json()) as LibraryListResponse;
  },

  async deleteLibraryEntry(
    creatorId: string,
    videoId: string,
    signal?: AbortSignal,
  ): Promise<{ creator_id: string; video_id: string; library_size: number }> {
    const res = await fetch(
      url(`/library/${encodeURIComponent(creatorId)}/${encodeURIComponent(videoId)}`),
      { method: 'DELETE', signal },
    );
    if (!res.ok) throw new BrainClientError(`/library/${creatorId}/${videoId} → ${res.status}`);
    return (await res.json()) as { creator_id: string; video_id: string; library_size: number };
  },

  async getInspiration(creatorId: string, signal?: AbortSignal): Promise<InspirationResponse> {
    const res = await fetch(url(`/inspiration/${encodeURIComponent(creatorId)}`), { signal });
    if (!res.ok) throw new BrainClientError(`/inspiration/${creatorId} → ${res.status}`);
    return (await res.json()) as InspirationResponse;
  },

  predictSimilarity(
    jobId: string,
    creatorId: string,
    opts?: { lastN?: number | null; sinceDays?: number | null },
    signal?: AbortSignal,
  ): Promise<SimilarityResponse> {
    const body: {
      job_id: string;
      creator_id: string;
      last_n?: number | null;
      since_days?: number | null;
    } = { job_id: jobId, creator_id: creatorId };
    if (opts?.lastN !== undefined) body.last_n = opts.lastN;
    if (opts?.sinceDays !== undefined) body.since_days = opts.sinceDays;
    return postJson<SimilarityResponse>('/similarity', body, signal);
  },

  resolveCacheUrl(pathOrUrl: string): string {
    if (pathOrUrl.startsWith('http')) return pathOrUrl;
    return `${BASE.replace(/\/$/, '')}${pathOrUrl}`;
  },

  streamUrl(jobId: string): string {
    return url(`/stream/${jobId}`);
  },
};

export interface AnalysisStreamHandlers {
  onStarted?: (msg: { mode: string; estimated_ms: number }) => void;
  onTranscript?: (words: TranscriptWord[]) => void;
  onBrainFrame?: (frame: BrainFrame) => void;
  onColdZones?: (zones: ColdZone[]) => void;
  onSuggestions?: (items: EditSuggestion[]) => void;
  onComplete?: (payload: Record<string, unknown>) => void;
  onError?: (err: Event | string) => void;
}

export function subscribeAnalysis(streamUrl: string, h: AnalysisStreamHandlers): () => void {
  const es = new EventSource(streamUrl);
  let completed = false;
  const safe = <T,>(fn: ((arg: T) => void) | undefined) => (e: MessageEvent) => {
    if (!fn) return;
    try {
      fn(JSON.parse(e.data));
    } catch (err) {
      console.error('[brainClient] event parse failed', err);
    }
  };
  es.addEventListener('started', safe(h.onStarted));
  es.addEventListener('transcript', (e: MessageEvent) => h.onTranscript?.(JSON.parse(e.data).words));
  es.addEventListener('brain_frame', safe(h.onBrainFrame));
  es.addEventListener('cold_zones', (e: MessageEvent) => h.onColdZones?.(JSON.parse(e.data).zones));
  es.addEventListener('suggestions', (e: MessageEvent) =>
    h.onSuggestions?.(JSON.parse(e.data).suggestions),
  );
  es.addEventListener('complete', (e: MessageEvent) => {
    completed = true;
    try {
      h.onComplete?.(JSON.parse(e.data));
    } catch (err) {
      console.error('[brainClient] complete parse failed', err);
    }
    es.close();
  });
  // EventSource fires `error` on every disconnect — including a clean server close
  // right after `complete`. Suppress those to avoid false "stream error" messages.
  es.addEventListener('error', (e) => {
    if (completed || es.readyState === EventSource.CLOSED) return;
    h.onError?.(e);
    es.close();
  });
  return () => es.close();
}

