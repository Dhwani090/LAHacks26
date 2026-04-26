// SimilarityPanel — top-3 most-similar past clips from the creator's library.
// PRD §11.6 + §7.5. Hidden when library < SIMILARITY_MIN_LIBRARY_SIZE (5).
// Renders <100ms after EngagementCard lands; numpy cosine on the GX10 is the bottleneck.
// See docs/PRD.md §11.6.
'use client';

import { useEffect, useState } from 'react';
import { brainClient } from '../lib/brainClient';
import { TUNING } from '../lib/tuning';
import type { RoiName, SimilarityMatch, SimilarityResponse } from '../lib/types';

interface Props {
  jobId: string | null;
  creatorId: string;
  // Bumping this prop refetches — used to refresh after a new library upload.
  refreshKey?: number;
}

const ROI_LABEL: Record<RoiName, string> = {
  visual: 'visual',
  auditory: 'auditory',
  language: 'language',
};

function formatScore(score: number): string {
  return `${Math.round(score * 100)}%`;
}

function formatUploaded(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return iso;
  }
}

export function SimilarityPanel({ jobId, creatorId, refreshKey = 0 }: Props) {
  const [data, setData] = useState<SimilarityResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openMatch, setOpenMatch] = useState<SimilarityMatch | null>(null);

  useEffect(() => {
    if (!jobId || !creatorId) {
      setData(null);
      return;
    }
    const ac = new AbortController();
    setLoading(true);
    setError(null);
    brainClient
      .predictSimilarity(jobId, creatorId, ac.signal)
      .then((res) => setData(res))
      .catch((err) => {
        if (ac.signal.aborted) return;
        console.error('[SimilarityPanel] /similarity failed', err);
        setError(err instanceof Error ? err.message : 'similarity failed');
      })
      .finally(() => setLoading(false));
    return () => ac.abort();
  }, [jobId, creatorId, refreshKey]);

  if (!jobId) return null;

  if (loading && !data) {
    return (
      <div className="rounded-md border border-white/10 bg-white/5 p-4 text-xs text-white/40">
        ranking your library…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md border border-red-500/20 bg-red-500/5 p-4 text-xs text-red-300">
        originality search failed — {error}
      </div>
    );
  }

  if (!data) return null;

  // Cold-start gate — hide entirely with a small hint instead of empty state.
  if (data.library_size < TUNING.SIMILARITY_MIN_LIBRARY_SIZE) {
    const need = TUNING.SIMILARITY_MIN_LIBRARY_SIZE - data.library_size;
    return (
      <div className="rounded-md border border-dashed border-white/10 bg-white/[0.02] p-4 text-xs text-white/40">
        upload {need} more past clip{need === 1 ? '' : 's'} to unlock originality search
      </div>
    );
  }

  if (data.matches.length === 0) return null;

  return (
    <>
      <div className="flex flex-col gap-3 rounded-md border border-white/10 bg-white/5 p-4">
        <div className="flex items-baseline justify-between">
          <div className="text-xs uppercase tracking-[0.2em] text-white/50">originality</div>
          <div className="text-[10px] text-white/30">
            ranked vs. {data.library_size} past clips
          </div>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {data.matches.map((m) => (
            <button
              key={m.video_id}
              type="button"
              onClick={() => setOpenMatch(m)}
              className="group flex flex-col items-start gap-2 rounded-md border border-white/10 bg-black/20 p-3 text-left transition-colors hover:border-orange-400/30 hover:bg-orange-400/5"
            >
              <div className="flex w-full items-center justify-between">
                <div className="text-sm font-medium text-white/85">{formatScore(m.score)} match</div>
                <div className="text-[10px] uppercase tracking-[0.18em] text-orange-300/80">
                  {ROI_LABEL[m.dominant_roi]}
                </div>
              </div>
              <div className="text-[11px] text-white/40">{formatUploaded(m.uploaded_at)}</div>
              <div className="flex w-full gap-1 text-[10px] text-white/40">
                <span>V {Math.round(m.roi_breakdown.visual * 100)}</span>
                <span>·</span>
                <span>A {Math.round(m.roi_breakdown.auditory * 100)}</span>
                <span>·</span>
                <span>L {Math.round(m.roi_breakdown.language * 100)}</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {openMatch && <MatchDrawer match={openMatch} onClose={() => setOpenMatch(null)} />}
    </>
  );
}

function MatchDrawer({ match, onClose }: { match: SimilarityMatch; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-40 flex items-stretch justify-end bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        className="flex h-full w-full max-w-md flex-col gap-4 border-l border-white/10 bg-zinc-950 p-6 text-white/85"
      >
        <div className="flex items-center justify-between">
          <div className="text-xs uppercase tracking-[0.22em] text-white/50">match details</div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-white/15 px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-white/60 hover:bg-white/5"
          >
            close
          </button>
        </div>
        <div className="text-2xl font-semibold text-orange-300">{formatScore(match.score)} brain match</div>
        <div className="grid grid-cols-2 gap-y-2 text-xs text-white/60">
          <div>video id</div>
          <div className="text-right text-white/85">{match.video_id}</div>
          <div>uploaded</div>
          <div className="text-right text-white/85">{formatUploaded(match.uploaded_at)}</div>
          <div>duration</div>
          <div className="text-right text-white/85">{match.duration_s.toFixed(1)}s</div>
          <div>dominant ROI</div>
          <div className="text-right text-white/85">{ROI_LABEL[match.dominant_roi]}</div>
          <div>text similarity</div>
          <div className="text-right text-white/85">{formatScore(match.text_similarity)}</div>
        </div>
        <div className="mt-2 flex flex-col gap-1 rounded-md border border-white/10 bg-white/5 p-3 text-xs">
          <div className="text-white/50 uppercase tracking-[0.18em] text-[10px]">ROI breakdown</div>
          <RoiBar label="visual" value={match.roi_breakdown.visual} />
          <RoiBar label="auditory" value={match.roi_breakdown.auditory} />
          <RoiBar label="language" value={match.roi_breakdown.language} />
        </div>
      </aside>
    </div>
  );
}

function RoiBar({ label, value }: { label: string; value: number }) {
  // Cosine in [-1, 1] → bar in [0, 100].
  const pct = Math.round(((value + 1) / 2) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 text-white/60">{label}</div>
      <div className="relative h-1.5 flex-1 rounded-full bg-white/10">
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-orange-400/70"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="w-10 text-right text-white/85">{Math.round(value * 100)}</div>
    </div>
  );
}
