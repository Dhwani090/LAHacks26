// EngagementCard — fetches /predict-engagement and renders the predicted
// engagement rate, percentile, and one-line interpretation.
// PRD §7.4 + §11.1 — gated behind an explicit "Predict Engagement" button on
// the /predict page; the user picks when to run the predictor (it's a
// separate side-trip from TRIBE inference and uses cached pooled features).
// See docs/PRD.md §7.4.
'use client';

import { useState } from 'react';
import { brainClient } from '../lib/brainClient';
import type { PredictEngagementResponse } from '../lib/types';

interface Props {
  jobId: string | null;
}

function bandLabel(percentile: number): string {
  if (percentile >= 75) return 'top quartile';
  if (percentile >= 50) return 'above median';
  if (percentile >= 25) return 'below median';
  return 'bottom quartile';
}

export function EngagementCard({ jobId }: Props) {
  const [followers, setFollowers] = useState<string>('');
  const [data, setData] = useState<PredictEngagementResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handlePredict() {
    if (!jobId) return;
    setLoading(true);
    setError(null);
    try {
      const followersInt = followers.trim() ? Math.max(0, Math.floor(Number(followers))) : 0;
      const res = await brainClient.predictEngagement(jobId, followersInt);
      setData(res);
    } catch (err) {
      console.error('[EngagementCard] predict failed', err);
      setError(err instanceof Error ? err.message : 'predict failed');
    } finally {
      setLoading(false);
    }
  }

  if (!jobId) return null;

  return (
    <div className="flex flex-col gap-3 rounded-md border border-white/10 bg-white/5 p-4">
      <div className="flex items-baseline justify-between">
        <div className="text-xs uppercase tracking-[0.2em] text-white/55">engagement</div>
        {data && (
          <div className="text-[10px] text-white/30">
            trained on {data.corpus_size} clips · {data.predictor_version}
          </div>
        )}
      </div>

      {!data && !loading && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex flex-1 flex-col gap-1 text-xs text-white/55">
            followers (optional)
            <input
              type="number"
              inputMode="numeric"
              value={followers}
              onChange={(e) => setFollowers(e.target.value)}
              placeholder="defaults to corpus median"
              className="rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-white/85 placeholder-white/25 outline-none transition-colors focus:border-orange-400/60"
            />
          </label>
          <button
            type="button"
            onClick={handlePredict}
            className="rounded-full border border-orange-400/60 bg-orange-400/10 px-5 py-2 text-xs font-medium uppercase tracking-[0.2em] text-orange-200 transition-colors hover:bg-orange-400/20"
          >
            Predict Engagement
          </button>
        </div>
      )}

      {loading && <div className="text-xs text-white/50">running predictor…</div>}

      {error && (
        <div className="rounded-md border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-300">
          {error}
        </div>
      )}

      {data && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-baseline gap-3">
            <div className="text-4xl font-semibold tabular-nums text-orange-300">
              {(data.predicted_rate * 100).toFixed(1)}%
            </div>
            <div className="text-xs uppercase tracking-[0.18em] text-white/45">
              expected views / followers
            </div>
          </div>
          <div className="text-sm text-white/85">
            {data.percentile}th percentile · {bandLabel(data.percentile)}
          </div>
          <div className="text-sm leading-snug text-white/65">{data.interpretation}</div>
          <div className="grid grid-cols-3 gap-2 text-[11px] text-white/40">
            <div>
              <div className="uppercase tracking-[0.18em] text-[9px]">followers used</div>
              <div className="text-white/80">{data.followers_used.toLocaleString()}</div>
            </div>
            <div>
              <div className="uppercase tracking-[0.18em] text-[9px]">duration</div>
              <div className="text-white/80">{data.duration_s.toFixed(1)}s</div>
            </div>
            <div>
              <div className="uppercase tracking-[0.18em] text-[9px]">cold zones</div>
              <div className="text-white/80">{data.n_cold_zones}</div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              setData(null);
              setError(null);
            }}
            className="self-start rounded-full border border-white/15 px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-white/55 hover:border-white/30 hover:text-white/85"
          >
            re-predict
          </button>
        </div>
      )}
    </div>
  );
}
