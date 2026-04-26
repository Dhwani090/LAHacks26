// InspirationFeed — third demo pillar: "what should I make next?"
// PRD §11.8 — ranks the curator's trending YouTube Shorts pool against
// the creator's centroid (computed server-side), surfaces top-3.
// Cold-start (library < 5) → returns null (the /library page header already
// shows a "need N more" indicator). Trending-empty → friendly placeholder.
// See docs/PRD.md §11.8.
'use client';

import { useEffect, useState } from 'react';
import { brainClient } from '../lib/brainClient';
import type { InspirationRecommendation, InspirationResponse, RoiName } from '../lib/types';

interface Props {
  creatorId: string;
}

// ROI track colors — match BrainMonitor + EngagementTimeline so a creator's
// brain pane and inspiration cards speak the same visual language.
const ROI_COLORS: Record<RoiName, { swatch: string; chip: string; gradient: string }> = {
  visual: {
    swatch: '#a78bfa',
    chip: 'border-violet-400/40 bg-violet-400/10 text-violet-200',
    gradient: 'from-violet-500/40 via-violet-700/30 to-zinc-900',
  },
  auditory: {
    swatch: '#34d399',
    chip: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-200',
    gradient: 'from-emerald-500/40 via-emerald-700/30 to-zinc-900',
  },
  language: {
    swatch: '#fb923c',
    chip: 'border-orange-400/40 bg-orange-400/10 text-orange-200',
    gradient: 'from-orange-500/40 via-orange-700/30 to-zinc-900',
  },
};

function formatViews(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return String(n);
}

export function InspirationFeed({ creatorId }: Props) {
  const [data, setData] = useState<InspirationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    brainClient
      .getInspiration(creatorId, ctrl.signal)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        if (ctrl.signal.aborted) return;
        console.error('[InspirationFeed] fetch failed', err);
        setError(err instanceof Error ? err.message : 'fetch failed');
        setLoading(false);
      });
    return () => ctrl.abort();
  }, [creatorId]);

  // Cold-start: library is too small. The /library page header already shows
  // "need N more" — we hide the section to avoid double-messaging the user.
  if (data && data.message && data.message.toLowerCase().includes('upload at least')) {
    return null;
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold text-white/85">What to make next</h2>
        <div className="text-[11px] uppercase tracking-[0.22em] text-white/40">
          {data
            ? `trending Shorts · ${data.trending_pool_size} in pool`
            : loading
            ? 'loading…'
            : ''}
        </div>
      </div>
      <p className="text-xs text-white/45">
        Trending YouTube Shorts ranked against your library&apos;s brain centroid.
        Click a card to open the original.
      </p>

      {error && (
        <div className="rounded-md border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-300">
          {error}
        </div>
      )}

      {loading && !error && <SkeletonRow />}

      {!loading && !error && data && data.recommendations.length === 0 && (
        <div className="rounded-md border border-dashed border-white/10 bg-white/[0.02] p-6 text-center text-sm text-white/45">
          {data.message ?? "trending pool not yet populated by curator — check back later"}
        </div>
      )}

      {!loading && !error && data && data.recommendations.length > 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.recommendations.map((rec) => (
            <InspirationCard key={rec.video_id} rec={rec} />
          ))}
        </div>
      )}
    </section>
  );
}

function InspirationCard({ rec }: { rec: InspirationRecommendation }) {
  const [thumbBroken, setThumbBroken] = useState(false);
  const tone = ROI_COLORS[rec.dominant_roi];
  const scorePct = Math.round(Math.max(0, Math.min(1, rec.score)) * 100);

  const inner = (
    <article className="group flex h-full flex-col overflow-hidden rounded-md border border-white/10 bg-zinc-950/60 transition-colors hover:border-white/25 hover:bg-zinc-950">
      <div className={`relative aspect-video w-full bg-gradient-to-br ${tone.gradient}`}>
        {!thumbBroken && rec.thumbnail_url && (
          <img
            src={rec.thumbnail_url}
            alt=""
            className="h-full w-full object-cover"
            onError={() => setThumbBroken(true)}
            // YouTube's CDN returns a 120×90 placeholder PNG (200 OK) for
            // missing/deleted video IDs, so onError never fires. Detect the
            // placeholder via natural dimensions instead — real hqdefault is
            // 480×360. Anything noticeably smaller is YouTube saying "video gone".
            onLoad={(e) => {
              const img = e.currentTarget;
              if (img.naturalWidth > 0 && img.naturalWidth < 200) {
                setThumbBroken(true);
              }
            }}
            loading="lazy"
          />
        )}
        <div className="absolute right-2 top-2 rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-medium tabular-nums text-white/90 backdrop-blur-sm">
          {scorePct}% match
        </div>
      </div>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] ${tone.chip}`}
          >
            <span
              aria-hidden
              className="h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: tone.swatch }}
            />
            {rec.dominant_roi}
          </span>
          {rec.view_count > 0 && (
            <span className="text-[10px] tabular-nums text-white/40">
              {formatViews(rec.view_count)} views
            </span>
          )}
        </div>
        {rec.creator_handle && (
          <div className="truncate text-xs text-white/60">{rec.creator_handle}</div>
        )}
        <div className="mt-auto flex items-baseline justify-between text-[10px] text-white/35">
          <span className="uppercase tracking-[0.18em]">view source ↗</span>
          <span className="tabular-nums">
            {rec.engagement_rate > 0 ? `${(rec.engagement_rate * 100).toFixed(1)}% eng` : ''}
          </span>
        </div>
      </div>
    </article>
  );

  if (!rec.source_url) {
    return inner;
  }
  return (
    <a
      href={rec.source_url}
      target="_blank"
      rel="noopener noreferrer"
      className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-white/30"
      title={`open ${rec.video_id} on YouTube`}
    >
      {inner}
    </a>
  );
}

function SkeletonRow() {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="h-48 animate-pulse rounded-md border border-white/10 bg-white/[0.03]"
        />
      ))}
    </div>
  );
}
