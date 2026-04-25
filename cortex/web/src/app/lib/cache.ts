// Local cache fallback — used when backend is down or analysis times out.
// PRD §12 (cache + fallback) + §13 R7 (GX10 dies mid-demo).
// Hero JSONs ship with the app under /public/cache/hero_*; this loader fetches them on demand.
// "Live" results land in sessionStorage (cleared on tab close).
// See docs/PRD.md §12.

import type { BrainFrame, ColdZone, EditSuggestion } from './types';

export interface CachedAnalysis {
  mode: 'text' | 'audio' | 'video';
  duration_s: number;
  brain_frames: BrainFrame[];
  engagement_curves: Record<string, number[]>;
  cold_zones: ColdZone[];
  suggestions?: EditSuggestion[];
}

const memCache = new Map<string, CachedAnalysis>();

export async function loadHero(
  mode: 'text' | 'audio' | 'video',
  slug: string,
): Promise<CachedAnalysis | null> {
  const key = `hero_${mode}:${slug}`;
  const cached = memCache.get(key);
  if (cached) return cached;
  try {
    const res = await fetch(`/cache/hero_${mode}/${slug}.json`);
    if (!res.ok) return null;
    const data = (await res.json()) as CachedAnalysis;
    memCache.set(key, data);
    return data;
  } catch (err) {
    console.error('[cache] loadHero failed', err);
    return null;
  }
}

export function rememberLive(key: string, payload: CachedAnalysis): void {
  memCache.set(`live:${key}`, payload);
  try {
    sessionStorage.setItem(`cortex:live:${key}`, JSON.stringify(payload));
  } catch {
    // sessionStorage may be disabled — silently drop.
  }
}

export function recallLive(key: string): CachedAnalysis | null {
  const mem = memCache.get(`live:${key}`);
  if (mem) return mem;
  try {
    const raw = sessionStorage.getItem(`cortex:live:${key}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedAnalysis;
    memCache.set(`live:${key}`, parsed);
    return parsed;
  } catch {
    return null;
  }
}
