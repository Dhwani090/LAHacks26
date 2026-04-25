// AutoImproveButton — the demo money beat: V1 → V2 → V3.
// PRD §7.4 (auto-improve UX) + §11 (streaming reasoning fills the dead air).
// On click: POST /auto-improve, subscribe /stream-improve, surface streaming reasoning,
// swap video src on cut_applied, re-pulse brain on brain_frame, advance version on complete.
// Parent (VideoSurface) provides clipId + onVersionChange callback.
'use client';

import { useEffect, useRef, useState } from 'react';
import { brainClient, subscribeAutoImprove } from '../lib/brainClient';
import { frameBus } from '../lib/frameBus';
import { useAppState } from '../state/AppState';
import type { ColdZone, EngagementCurves } from '../lib/types';

interface Props {
  clipId: string | null;
  disabled?: boolean;
  onVersionChange?: (version: number, videoUrl: string) => void;
}

type ImproveStatus = 'idle' | 'reasoning' | 'cutting' | 'reanalyzing' | 'done' | 'error';

export function AutoImproveButton({ clipId, disabled, onVersionChange }: Props) {
  const [version, setVersion] = useState(1);
  const [status, setStatus] = useState<ImproveStatus>('idle');
  const [reasoning, setReasoning] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const setColdZones = useAppState((s) => s.setColdZones);
  const setEngagementCurves = useAppState((s) => s.setEngagementCurves);
  const setSuggestions = useAppState((s) => s.setSuggestions);

  const unsubRef = useRef<(() => void) | null>(null);
  useEffect(() => () => unsubRef.current?.(), []);

  const busy =
    status === 'reasoning' || status === 'cutting' || status === 'reanalyzing';
  const ctaDisabled = disabled || busy || !clipId || version >= 3;

  function reset() {
    unsubRef.current?.();
    setVersion(1);
    setStatus('idle');
    setReasoning('');
    setErrorMsg(null);
  }

  async function handleClick() {
    if (ctaDisabled || !clipId) return;
    setErrorMsg(null);
    setReasoning('');
    setStatus('reasoning');

    let job;
    try {
      job = await brainClient.autoImprove(clipId, version);
    } catch (err) {
      console.error('[AutoImproveButton] start failed', err);
      setErrorMsg(err instanceof Error ? err.message : 'auto-improve failed');
      setStatus('error');
      return;
    }

    frameBus.reset();

    unsubRef.current = subscribeAutoImprove(brainClient.streamImproveUrl(job.job_id), {
      onReasoning: (token) => {
        setStatus((cur) => (cur === 'idle' || cur === 'error' ? 'reasoning' : cur));
        setReasoning((cur) => cur + token);
      },
      onCutting: () => setStatus('cutting'),
      onCutApplied: (v2Url) => {
        const next = version + 1;
        setVersion(next);
        onVersionChange?.(next, v2Url);
      },
      onReanalyzing: () => setStatus('reanalyzing'),
      onBrainFrame: (frame) => frameBus.publish(frame),
      onComplete: (payload) => {
        const curves = (payload?.v2_engagement ?? payload?.engagement_curves) as
          | EngagementCurves
          | undefined;
        const zones = (payload?.v2_cold_zones ?? payload?.cold_zones) as
          | ColdZone[]
          | undefined;
        if (curves) setEngagementCurves(curves);
        if (zones) setColdZones(zones);
        setSuggestions([]);
        setStatus('done');
      },
      onError: (err) => {
        console.error('[AutoImproveButton] stream error', err);
        setErrorMsg('auto-improve stream failed');
        setStatus('error');
      },
    });
  }

  const label = (() => {
    if (version >= 3 && status === 'done') return 'V3 — final';
    if (status === 'reasoning') return 'thinking…';
    if (status === 'cutting') return 'cutting…';
    if (status === 'reanalyzing') return 'reanalyzing…';
    if (version === 1) return 'Auto-improve';
    if (version === 2) return 'Improve again → V3';
    return `→ V${version + 1}`;
  })();

  return (
    <div className="flex w-full flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-[0.25em] text-white/40">
          version {version}
          {status === 'done' && version > 1 && (
            <span className="ml-2 text-emerald-300">brain healthier</span>
          )}
          {errorMsg && <span className="ml-2 text-red-400">{errorMsg}</span>}
        </span>
        <div className="flex gap-2">
          {version > 1 && (
            <button
              type="button"
              onClick={reset}
              disabled={busy}
              className="rounded-full border border-white/15 px-4 py-1.5 text-[11px] uppercase tracking-[0.2em] text-white/60 transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
            >
              reset to V1
            </button>
          )}
          <button
            type="button"
            onClick={handleClick}
            disabled={ctaDisabled}
            className="rounded-full border border-emerald-400/60 bg-emerald-400/10 px-5 py-2 text-xs font-medium uppercase tracking-[0.2em] text-emerald-200 transition-colors hover:bg-emerald-400/20 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-transparent disabled:text-white/30"
          >
            {label}
          </button>
        </div>
      </div>

      {(reasoning || busy) && (
        <div className="max-h-[120px] overflow-y-auto rounded-md border border-emerald-400/20 bg-emerald-400/[0.03] p-3 font-mono text-[11px] leading-relaxed text-emerald-100/80">
          {reasoning || (
            <span className="text-white/30">streaming reasoning from Gemma…</span>
          )}
          {busy && <span className="ml-1 inline-block animate-pulse text-emerald-300">▋</span>}
        </div>
      )}
    </div>
  );
}
