// TextSurface — paste-and-diagnose UI for text mode.
// PRD §6.1 (text mode) + §7 — heatmap (P1-05) and suggestions (P1-07) live here later.
// P1-03: real backend wire-up. POST /analyze/text → subscribe /stream/{job_id} →
//   route brain frames to frameBus, status/cold zones/suggestions to AppState.
// Errors surface to AppState.errorMessage; UI degrades, frontend never crashes.
// See docs/PRD.md §6.1.
'use client';

import { useEffect, useRef, useState } from 'react';
import { brainClient, subscribeAnalysis } from '../lib/brainClient';
import { frameBus } from '../lib/frameBus';
import { TUNING } from '../lib/tuning';
import { useAppState } from '../state/AppState';
import { HeatmapText } from './HeatmapText';

const HERO_SAMPLE =
  'Most creators ship work and wait two weeks for analytics to know if it landed. ' +
  'But here is the part nobody talks about: the middle of any draft is where readers quietly leave. ' +
  'Cortex closes the loop by predicting the average viewer brain response in seconds, not weeks.';

export function TextSurface() {
  const [text, setText] = useState(HERO_SAMPLE);
  const status = useAppState((s) => s.status);
  const errorMessage = useAppState((s) => s.errorMessage);
  const setStatus = useAppState((s) => s.setStatus);
  const setJobId = useAppState((s) => s.setJobId);
  const setColdZones = useAppState((s) => s.setColdZones);
  const setSuggestions = useAppState((s) => s.setSuggestions);
  const setError = useAppState((s) => s.setError);
  const resetAnalysis = useAppState((s) => s.resetAnalysis);

  const unsubRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => {
      unsubRef.current?.();
    };
  }, []);

  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;
  const overLimit = wordCount > TUNING.MAX_TEXT_WORDS;
  const busy = status === 'submitting' || status === 'streaming';

  async function handleDiagnose() {
    if (busy || overLimit || wordCount === 0) return;

    unsubRef.current?.();
    resetAnalysis();
    frameBus.reset();
    setStatus('submitting');

    try {
      const job = await brainClient.analyzeText(text);
      setJobId(job.job_id);
      setStatus('streaming');

      unsubRef.current = subscribeAnalysis(brainClient.streamUrl(job.job_id), {
        onBrainFrame: (frame) => frameBus.publish(frame),
        onColdZones: (zones) => setColdZones(zones),
        onSuggestions: (items) => setSuggestions(items),
        onComplete: () => setStatus('complete'),
        onError: (err) => {
          console.error('[TextSurface] stream error', err);
          setError('stream error — backend may be down');
        },
      });
    } catch (err) {
      console.error('[TextSurface] analyze failed', err);
      setError(err instanceof Error ? err.message : 'analyze failed');
    }
  }

  function handleEditAgain() {
    unsubRef.current?.();
    resetAnalysis();
    frameBus.reset();
  }

  const showHeatmap = status === 'streaming' || status === 'complete';

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="flex min-h-0 flex-1 flex-col">
        {showHeatmap ? (
          <HeatmapText text={text} />
        ) : (
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={busy}
            placeholder="Paste up to 500 words. The brain will tell you which sentences landed."
            className="min-h-0 flex-1 resize-none rounded-md border border-white/10 bg-black/30 p-4 text-sm leading-relaxed text-white/90 placeholder:text-white/30 focus:border-orange-400/60 focus:outline-none disabled:opacity-60"
          />
        )}
      </div>
      <div className="flex shrink-0 items-center justify-between text-xs text-white/50">
        <div className="flex items-center gap-3">
          <span className={overLimit ? 'text-red-400' : ''}>
            {wordCount} / {TUNING.MAX_TEXT_WORDS} words
          </span>
          {status === 'streaming' && (
            <span className="text-orange-300">streaming…</span>
          )}
          {status === 'complete' && (
            <span className="text-emerald-300">complete</span>
          )}
          {errorMessage && <span className="text-red-400">{errorMessage}</span>}
        </div>
        {showHeatmap ? (
          <button
            type="button"
            onClick={handleEditAgain}
            className="rounded-full border border-white/15 px-5 py-2 text-xs font-medium uppercase tracking-[0.2em] text-white/70 transition-colors hover:bg-white/5"
          >
            Edit again
          </button>
        ) : (
          <button
            type="button"
            onClick={handleDiagnose}
            disabled={busy || wordCount === 0 || overLimit}
            className="rounded-full border border-orange-400/60 bg-orange-400/10 px-5 py-2 text-xs font-medium uppercase tracking-[0.2em] text-orange-200 transition-colors hover:bg-orange-400/20 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-transparent disabled:text-white/30"
          >
            {busy ? 'analyzing…' : 'Diagnose'}
          </button>
        )}
      </div>
    </div>
  );
}
