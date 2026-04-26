// AddToLibraryButton — one-click "save this draft to my library" after a
// video analysis completes on /predict.
// PRD §11.6 — calls POST /library/from-job which reuses the cached pooled
// features + transcript embedding from the analysis job (no re-run of
// TRIBE/Whisper on the GX10).
// Optional rename input lets the user label the entry; default is the
// source filename stem from the upload.
// See docs/PRD.md §11.6.
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { brainClient } from '../lib/brainClient';

interface Props {
  jobId: string | null;
  creatorId: string;
  defaultName?: string;
  onAdded?: (librarySize: number) => void;
}

type Phase = 'idle' | 'naming' | 'saving' | 'saved' | 'error';

export function AddToLibraryButton({ jobId, creatorId, defaultName, onAdded }: Props) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [name, setName] = useState(defaultName ?? '');
  const [savedAs, setSavedAs] = useState<{ id: string; size: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!jobId) return null;

  async function handleSave() {
    if (!jobId) return;
    setPhase('saving');
    setError(null);
    try {
      const res = await brainClient.addJobToLibrary(jobId, creatorId, name);
      setSavedAs({ id: res.library_entry_id, size: res.library_size });
      setPhase('saved');
      onAdded?.(res.library_size);
    } catch (err) {
      console.error('[AddToLibraryButton] /library/from-job failed', err);
      setError(err instanceof Error ? err.message : 'save failed');
      setPhase('error');
    }
  }

  if (phase === 'saved' && savedAs) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-md border border-emerald-400/30 bg-emerald-400/5 p-3 text-xs">
        <div className="text-emerald-300">
          Added <span className="font-mono text-emerald-200">{savedAs.id}</span> to your library
          {' '}— {savedAs.size} clip{savedAs.size === 1 ? '' : 's'} total.
        </div>
        <Link
          href="/library"
          className="rounded-full border border-emerald-400/40 px-3 py-1 uppercase tracking-[0.2em] text-emerald-200 hover:bg-emerald-400/10"
        >
          view library
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-white/10 bg-white/[0.04] p-4">
      <div className="flex items-baseline justify-between">
        <div className="text-xs uppercase tracking-[0.2em] text-white/55">post it?</div>
        <div className="text-[10px] text-white/35">
          saves features only — no raw video stored
        </div>
      </div>
      <p className="text-xs text-white/55">
        Like the brain you saw? Add this draft to your library so future drafts can be ranked against it for originality.
      </p>
      {phase === 'naming' ? (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={defaultName ?? 'name this clip'}
            className="flex-1 rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-white/85 placeholder-white/25 outline-none focus:border-emerald-400/60"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setPhase('idle')}
              className="rounded-full border border-white/15 px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] text-white/55 hover:bg-white/5"
            >
              cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="rounded-full border border-emerald-400/60 bg-emerald-400/10 px-4 py-1.5 text-[10px] uppercase tracking-[0.2em] text-emerald-200 hover:bg-emerald-400/20"
            >
              save
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={phase === 'saving'}
            className="rounded-full border border-emerald-400/60 bg-emerald-400/10 px-4 py-2 text-xs font-medium uppercase tracking-[0.2em] text-emerald-200 transition-colors hover:bg-emerald-400/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {phase === 'saving' ? 'saving…' : 'Add to Library'}
          </button>
          <button
            type="button"
            onClick={() => setPhase('naming')}
            disabled={phase === 'saving'}
            className="rounded-full border border-white/15 px-4 py-2 text-xs uppercase tracking-[0.2em] text-white/55 transition-colors hover:bg-white/5"
          >
            rename first
          </button>
        </div>
      )}
      {error && (
        <div className="text-xs text-red-300">{error}</div>
      )}
    </div>
  );
}
