// /library — past clips for the current creator (single-tenant demo build).
// PRD §11.6 — entries persist as TRIBE-pooled features + transcript embedding;
// raw mp4s are deleted after the upload pipeline. We surface the metadata
// the user cares about: duration + uploaded timestamp.
// LibraryUploader appends to the same list. SimilarityPanel cold-starts at 5.
// See docs/PRD.md §11.6.
'use client';

import { useCallback, useEffect, useState } from 'react';
import { AppShell } from '../components/AppShell';
import { InspirationFeed } from '../components/InspirationFeed';
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
  // Track per-row delete state so we can disable the button + show "removing…"
  // without a global spinner (the table can have 100+ rows).
  const [deleting, setDeleting] = useState<Set<string>>(new Set());
  const [pendingDelete, setPendingDelete] = useState<LibraryEntryMeta | null>(null);

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

  async function handleConfirmDelete(entry: LibraryEntryMeta) {
    setDeleting((prev) => new Set(prev).add(entry.video_id));
    // Optimistic remove — if the request fails we'll refetch on error.
    setEntries((prev) => prev.filter((e) => e.video_id !== entry.video_id));
    setPendingDelete(null);
    try {
      await brainClient.deleteLibraryEntry(DEMO_CREATOR_ID, entry.video_id);
    } catch (err) {
      console.error('[/library] delete failed', err);
      setError(err instanceof Error ? err.message : 'delete failed');
      // Restore real state — the optimistic removal might have been wrong.
      void refresh();
    } finally {
      setDeleting((prev) => {
        const next = new Set(prev);
        next.delete(entry.video_id);
        return next;
      });
    }
  }

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
                  <th className="w-10 px-2 py-2 font-medium text-right" aria-label="actions" />
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {entries.map((e) => {
                  const isDeleting = deleting.has(e.video_id);
                  return (
                    <tr key={e.video_id} className="group hover:bg-white/[0.03]">
                      <td className="px-4 py-3 font-mono text-xs text-white/85">{e.video_id}</td>
                      <td className="px-4 py-3 tabular-nums text-white/65">
                        {formatDuration(e.duration_s)}
                      </td>
                      <td className="px-4 py-3 text-white/65">
                        <div className="text-white/85">{relativeTime(e.uploaded_at)}</div>
                        <div className="text-[10px] text-white/40">{formatTimestamp(e.uploaded_at)}</div>
                      </td>
                      <td className="w-10 px-2 py-3 text-right">
                        <button
                          type="button"
                          onClick={() => setPendingDelete(e)}
                          disabled={isDeleting}
                          aria-label={`delete ${e.video_id}`}
                          title="remove from library"
                          className="rounded-full border border-transparent px-2 py-0.5 text-base leading-none text-white/30 transition-colors hover:border-red-400/40 hover:bg-red-400/10 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          {isDeleting ? '…' : '×'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {ready && <InspirationFeed creatorId={DEMO_CREATOR_ID} />}

        {pendingDelete && (
          <DeleteConfirm
            entry={pendingDelete}
            onCancel={() => setPendingDelete(null)}
            onConfirm={() => handleConfirmDelete(pendingDelete)}
          />
        )}
      </div>
    </AppShell>
  );
}

function DeleteConfirm({
  entry,
  onCancel,
  onConfirm,
}: {
  entry: LibraryEntryMeta;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex w-full max-w-sm flex-col gap-4 rounded-lg border border-white/10 bg-zinc-950 p-6 text-white/85"
      >
        <div className="text-xs uppercase tracking-[0.22em] text-white/50">remove from library?</div>
        <div className="flex flex-col gap-1">
          <div className="font-mono text-sm text-white/85">{entry.video_id}</div>
          <div className="text-xs text-white/45">
            Brain features + transcript will be deleted. This won&apos;t affect any
            past similarity searches you&apos;ve already viewed.
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-full border border-white/15 px-4 py-1.5 text-[11px] uppercase tracking-[0.2em] text-white/60 hover:bg-white/5"
          >
            cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-full border border-red-400/50 bg-red-400/10 px-4 py-1.5 text-[11px] uppercase tracking-[0.2em] text-red-300 hover:bg-red-400/20"
          >
            remove
          </button>
        </div>
      </div>
    </div>
  );
}
