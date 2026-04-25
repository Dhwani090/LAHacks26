// SuggestionPanel — Gemma rewrite for the picked cold sentence.
// PRD §6.1 (text mode) + §7 — completes the text-mode iteration loop.
// Receives the picked sentence + matching EditSuggestion; apply/reject buttons fire callbacks.
// Empty-suggestion path: panel renders an "offline" notice so the UI stays honest if Gemma is down.
// See docs/PRD.md §6.1.
'use client';

import type { EditSuggestion } from '../lib/types';

interface Props {
  pickedSentence: string;
  pickedIndex: number;
  suggestion: EditSuggestion | null;
  busy: boolean;
  onApply: (suggestion: EditSuggestion) => void;
  onReject: () => void;
}

export function SuggestionPanel({
  pickedSentence,
  pickedIndex,
  suggestion,
  busy,
  onApply,
  onReject,
}: Props) {
  return (
    <div className="rounded-md border border-orange-400/40 bg-orange-400/[0.04] p-4 text-sm">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-[10px] font-medium uppercase tracking-[0.25em] text-orange-200/80">
          Sentence {pickedIndex + 1} · cold zone
        </span>
        <button
          type="button"
          onClick={onReject}
          disabled={busy}
          className="text-[10px] uppercase tracking-[0.2em] text-white/40 hover:text-white/70 disabled:cursor-not-allowed disabled:opacity-40"
        >
          dismiss
        </button>
      </div>

      <p className="mb-3 rounded border border-blue-400/30 bg-blue-400/5 p-2 text-blue-100/80">
        {pickedSentence}
      </p>

      {suggestion ? (
        <>
          <div className="mb-2 text-[10px] uppercase tracking-[0.25em] text-white/40">
            Gemma suggests
          </div>
          <p className="mb-3 rounded border border-emerald-400/30 bg-emerald-400/5 p-2 text-emerald-100/90">
            {suggestion.rewrite ?? '(no rewrite returned)'}
          </p>
          {suggestion.rationale && (
            <p className="mb-3 text-xs leading-relaxed text-white/50">
              {suggestion.rationale}
            </p>
          )}
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onReject}
              disabled={busy}
              className="rounded-full border border-white/15 px-4 py-1.5 text-xs uppercase tracking-[0.2em] text-white/60 transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
            >
              keep
            </button>
            <button
              type="button"
              onClick={() => suggestion.rewrite && onApply(suggestion)}
              disabled={busy || !suggestion.rewrite}
              className="rounded-full border border-emerald-400/60 bg-emerald-400/10 px-4 py-1.5 text-xs font-medium uppercase tracking-[0.2em] text-emerald-200 transition-colors hover:bg-emerald-400/20 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-transparent disabled:text-white/30"
            >
              {busy ? 'applying…' : 'apply rewrite'}
            </button>
          </div>
        </>
      ) : (
        <p className="text-xs text-white/40">
          Gemma offline — no rewrite available for this sentence yet.
        </p>
      )}
    </div>
  );
}
