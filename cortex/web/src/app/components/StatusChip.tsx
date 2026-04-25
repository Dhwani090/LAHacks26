// StatusChip — GX10 connection indicator (top-right).
// PRD §13 R7 + §15 failure-mode pivots — chip turns gray on backend loss.
// Polls /health every TUNING.HEALTH_POLL_MS. Manual override via prop for demos.
// Hidden if NEXT_PUBLIC_BRAIN_BASE_URL is unset (early-dev safety).
// See docs/PRD.md §12 + §13.
'use client';

import { useEffect, useState } from 'react';
import { brainClient, type HealthResponse } from '../lib/brainClient';
import { TUNING } from '../lib/tuning';

type ChipState = 'live' | 'degraded' | 'offline' | 'unknown';

export function StatusChip() {
  const baseSet = Boolean(process.env.NEXT_PUBLIC_BRAIN_BASE_URL);
  const [state, setState] = useState<ChipState>(baseSet ? 'unknown' : 'offline');
  const [detail, setDetail] = useState<HealthResponse | null>(null);

  useEffect(() => {
    if (!baseSet) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      try {
        const ctl = new AbortController();
        const timeout = setTimeout(() => ctl.abort(), 3000);
        const h = await brainClient.health(ctl.signal);
        clearTimeout(timeout);
        if (cancelled) return;
        setDetail(h);
        // Foreign /health responses lack these fields → treat as degraded, not live.
        const looksLikeCortex =
          'tribe_loaded' in h && 'gemma_loaded' in h && 'gx10_uptime_s' in h;
        setState(
          looksLikeCortex && h.status === 'ok' && h.tribe_loaded && h.gemma_loaded
            ? 'live'
            : 'degraded',
        );
      } catch {
        if (!cancelled) {
          setState('offline');
          setDetail(null);
        }
      } finally {
        if (!cancelled) timer = setTimeout(poll, TUNING.HEALTH_POLL_MS);
      }
    };
    poll();

    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [baseSet]);

  const palette: Record<ChipState, string> = {
    live: 'bg-emerald-400/15 text-emerald-300 border-emerald-400/40',
    degraded: 'bg-amber-400/15 text-amber-300 border-amber-400/40',
    offline: 'bg-white/5 text-white/40 border-white/10',
    unknown: 'bg-white/5 text-white/40 border-white/10',
  };

  const label: Record<ChipState, string> = {
    live: 'GX10 · live',
    degraded: 'GX10 · loading',
    offline: 'GX10 · offline',
    unknown: 'GX10 · checking',
  };

  return (
    <div
      className={`flex items-center gap-2 rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.2em] ${palette[state]}`}
      title={
        detail && typeof detail.gx10_uptime_s === 'number'
          ? `uptime ${detail.gx10_uptime_s.toFixed(0)}s · cache ${detail.cache_size ?? 0}`
          : ''
      }
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          state === 'live'
            ? 'bg-emerald-400'
            : state === 'degraded'
              ? 'bg-amber-400'
              : 'bg-white/30'
        }`}
      />
      {label[state]}
    </div>
  );
}
