// /library — past clips for the current creator (single-tenant demo build).
// PRD §11.6 — entries persist as TRIBE-pooled features + transcript embedding;
// raw mp4s are deleted after the upload pipeline. We surface the metadata
// the user cares about: duration + uploaded timestamp.
// LibraryUploader appends to the same list. SimilarityPanel cold-starts at 5.
// See docs/PRD.md §11.6.
'use client';

import { useCallback, useEffect, useState } from 'react';
import { AppShell } from '../components/AppShell';
import { LibraryUploader } from '../components/LibraryUploader';
import { brainClient } from '../lib/brainClient';
import { DEMO_CREATOR_ID } from '../lib/creator';
import { TUNING } from '../lib/tuning';
import type { LibraryEntryMeta } from '../lib/types';

function formatDuration(s: number): string {
  if (!Number.isFinite(s) || s <= 0) return '—';
  const total = Math.round(s);
  const m = Math.floor(total / 60);
  const sec = total % 60;
  return m > 0 ? `${m}:${sec.toString().padStart(2, '0')}` : `${sec}s`;
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function relativeTime(iso: string): string {
  try {
    const then = new Date(iso).getTime();
    const now = Date.now();
    const diffSec = Math.max(1, Math.round((now - then) / 1000));
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.round(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.round(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.round(diffHr / 24);
    if (diffDay < 30) return `${diffDay}d ago`;
    const diffMo = Math.round(diffDay / 30);
    return `${diffMo}mo ago`;
  } catch {
    return '';
  }
}

export default function LibraryPage() {
  const [entries, setEntries] = useState<LibraryEntryMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const res = await brainClient.getLibrary(DEMO_CREATOR_ID);
      const sorted = [...res.entries].sort((a, b) => {
        return new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime();
      });
      setEntries(sorted);
    } catch (err) {
      console.error('[/library] load failed', err);
      setError(err instanceof Error ? err.message : 'load failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const need = Math.max(0, TUNING.SIMILARITY_MIN_LIBRARY_SIZE - entries.length);
  const ready = need === 0;

  return (
    <AppShell subtitle="your past clips · TRIBE features + transcripts only">
      <div className="flex min-h-0 flex-col gap-6 overflow-y-auto pr-1">
        <div className="flex flex-col gap-1">
          <div className="flex items-baseline justify-between">
            <h2 className="text-lg font-semibold text-white/85">Library</h2>
            <div className="text-[11px] uppercase tracking-[0.22em] text-white/40">
              {loading
                ? 'loading…'
                : ready
                ? `${entries.length} clip${entries.length === 1 ? '' : 's'} · ready`
                : `${entries.length} / ${TUNING.SIMILARITY_MIN_LIBRARY_SIZE} — need ${need} more`}
            </div>
          </div>
          <p className="text-xs text-white/45">
            Each clip is a TRIBE feature vector + Whisper transcript + embedding.
            Raw video is deleted after upload — only the brain signal stays on the box.
          </p>
        </div>

        <LibraryUploader creatorId={DEMO_CREATOR_ID} onLibraryChange={() => refresh()} />

        {error && (
          <div className="rounded-md border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-300">
            {error}
          </div>
        )}

        {!loading && entries.length === 0 && !error && (
          <div className="rounded-md border border-dashed border-white/10 bg-white/[0.02] p-8 text-center text-sm text-white/45">
            No clips yet. Upload {TUNING.SIMILARITY_MIN_LIBRARY_SIZE}+ to unlock originality search on /predict.
          </div>
        )}

        {entries.length > 0 && (
          <div className="overflow-hidden rounded-md border border-white/10">
            <table className="w-full text-left text-sm">
              <thead className="bg-white/5 text-[10px] uppercase tracking-[0.18em] text-white/45">
                <tr>
                  <th className="px-4 py-2 font-medium">Video ID</th>
                  <th className="px-4 py-2 font-medium">Length</th>
                  <th className="px-4 py-2 font-medium">Uploaded</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {entries.map((e) => (
                  <tr key={e.video_id} className="hover:bg-white/[0.03]">
                    <td className="px-4 py-3 font-mono text-xs text-white/85">{e.video_id}</td>
                    <td className="px-4 py-3 tabular-nums text-white/65">
                      {formatDuration(e.duration_s)}
                    </td>
                    <td className="px-4 py-3 text-white/65">
                      <div className="text-white/85">{relativeTime(e.uploaded_at)}</div>
                      <div className="text-[10px] text-white/40">{formatTimestamp(e.uploaded_at)}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  );
}
