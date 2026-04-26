// VideoSurface — drop-a-video-clip UI for video mode (the spectacle).
// PRD §6.3 (video mode) + §7 — player, 3-track timeline.
// On Diagnose: POST /analyze/video → subscribe /stream/{job_id} → frames to frameBus,
// engagement/cold zones to AppState.
// See docs/PRD.md §6.3.
'use client';

import { useEffect, useRef, useState } from 'react';
import { brainClient, subscribeAnalysis } from '../lib/brainClient';
import { frameBus } from '../lib/frameBus';
import { TUNING } from '../lib/tuning';
import { useAppState } from '../state/AppState';
import type { ColdZone, EngagementCurves, TranscriptWord } from '../lib/types';
import { EngagementTimeline } from './EngagementTimeline';
import { LibraryUploader } from './LibraryUploader';
import { SimilarityPanel } from './SimilarityPanel';

// Single-creator demo build — every upload goes into one library bucket.
// PRD §11.6 caveat: multi-tenant comes after the hackathon.
const DEMO_CREATOR_ID = 'demo';

type Phase = 'idle' | 'uploading' | 'tribe' | 'rendering' | 'feedback' | 'done';

const PHASE_LABEL: Record<Phase, string> = {
  idle: '',
  uploading: 'uploading clip',
  tribe: 'running TRIBE on GX10',
  rendering: 'painting cortical surface',
  feedback: 'gemma writing feedback',
  done: 'complete',
};

export function VideoSurface() {
  const [file, setFile] = useState<File | null>(null);
  const [videoSrc, setVideoSrc] = useState<string | null>(null);
  const [, setClipId] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [progress, setProgress] = useState(0);
  const [phase, setPhase] = useState<Phase>('idle');
  const progressTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const progressStartRef = useRef<number>(0);
  const progressEtaRef = useRef<number>(60_000);

  const status = useAppState((s) => s.status);
  const errorMessage = useAppState((s) => s.errorMessage);
  const coldZones = useAppState((s) => s.coldZones);
  const engagementCurves = useAppState((s) => s.engagementCurves);
  const durationS = useAppState((s) => s.durationS);
  const jobId = useAppState((s) => s.jobId);
  const suggestions = useAppState((s) => s.suggestions);
  const setStatus = useAppState((s) => s.setStatus);
  const setJobId = useAppState((s) => s.setJobId);
  const setColdZones = useAppState((s) => s.setColdZones);
  const setSuggestions = useAppState((s) => s.setSuggestions);
  const setEngagementCurves = useAppState((s) => s.setEngagementCurves);
  const setTranscript = useAppState((s) => s.setTranscript);
  const setDurationS = useAppState((s) => s.setDurationS);
  const setError = useAppState((s) => s.setError);
  const resetAnalysis = useAppState((s) => s.resetAnalysis);
  const [librarySize, setLibrarySize] = useState<number | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const unsubRef = useRef<(() => void) | null>(null);

  useEffect(() => () => unsubRef.current?.(), []);

  useEffect(() => {
    if (!file) {
      setVideoSrc(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setVideoSrc(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const busy = status === 'submitting' || status === 'streaming';
  const analyzed = status === 'streaming' || status === 'complete';

  const startProgress = (etaMs: number) => {
    if (progressTimerRef.current) clearInterval(progressTimerRef.current);
    progressStartRef.current = performance.now();
    progressEtaRef.current = Math.max(2_000, etaMs);
    setProgress(0.02);
    progressTimerRef.current = setInterval(() => {
      const elapsed = performance.now() - progressStartRef.current;
      // Asymptotic curve to 0.92 — never visually stalls at 100%, never lies that
      // we're done. The complete event snaps it to 1.0.
      const frac = 1 - Math.exp(-elapsed / progressEtaRef.current);
      setProgress(Math.min(0.92, 0.02 + frac * 0.9));
    }, 200);
  };

  const stopProgress = (final: number) => {
    if (progressTimerRef.current) clearInterval(progressTimerRef.current);
    progressTimerRef.current = null;
    setProgress(final);
  };

  useEffect(() => () => {
    if (progressTimerRef.current) clearInterval(progressTimerRef.current);
  }, []);

  function handleDiagnose() {
    if (!file || busy) return;

    unsubRef.current?.();
    resetAnalysis();
    frameBus.reset();
    setStatus('submitting');
    setPhase('uploading');
    startProgress(60_000);

    brainClient
      .analyzeVideo(file)
      .then((job) => {
        setJobId(job.job_id);
        setClipId(job.job_id);
        setStatus('streaming');
        setPhase('tribe');
        // Backend tells us the real ETA — 1s for cache hit, 600s for cold.
        startProgress(job.estimated_ms || 60_000);

        unsubRef.current = subscribeAnalysis(brainClient.streamUrl(job.job_id), {
          onTranscript: (words: TranscriptWord[]) => setTranscript(words),
          onBrainFrame: (frame) => {
            frameBus.publish(frame);
            setPhase('rendering');
          },
          onColdZones: (zones: ColdZone[]) => {
            setColdZones(zones);
            setPhase('feedback');
          },
          onSuggestions: (items) => setSuggestions(items),
          onComplete: (payload) => {
            const curves = payload?.engagement_curves as EngagementCurves | undefined;
            const dur = payload?.duration_s as number | undefined;
            if (curves) setEngagementCurves(curves);
            if (typeof dur === 'number') setDurationS(dur);
            setStatus('complete');
            setPhase('done');
            stopProgress(1);
          },
          onError: (err) => {
            console.error('[VideoSurface] stream error', err);
            setError('stream error — backend may be down');
            setPhase('idle');
            stopProgress(0);
          },
        });
      })
      .catch((err) => {
        console.error('[VideoSurface] analyze failed', err);
        setError(err instanceof Error ? err.message : 'analyze failed');
        setPhase('idle');
        stopProgress(0);
      });
  }

  function handlePickColdZone(zone: ColdZone) {
    if (videoRef.current) {
      videoRef.current.currentTime = zone.start;
      videoRef.current.play().catch(() => {});
    }
  }

  function handleTimeUpdate(e: React.SyntheticEvent<HTMLVideoElement>) {
    setCurrentTime(e.currentTarget.currentTime);
  }

  function handleLoadedMetadata(e: React.SyntheticEvent<HTMLVideoElement>) {
    const d = e.currentTarget.duration;
    if (Number.isFinite(d) && d > 0 && durationS === 0) {
      setDurationS(d);
    }
  }

  const fileTooLong =
    durationS > 0 && durationS > TUNING.MAX_MEDIA_SECONDS;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
        {videoSrc ? (
          <video
            ref={videoRef}
            key={videoSrc}
            src={videoSrc}
            controls
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={handleLoadedMetadata}
            className="max-h-[260px] w-full shrink-0 rounded-md bg-black object-contain"
          />
        ) : (
          <label className="flex min-h-[200px] flex-1 cursor-pointer flex-col items-center justify-center gap-3 rounded-md border border-dashed border-white/15 bg-black/20 p-6 text-center text-sm text-white/50 transition-colors hover:border-orange-400/40 hover:text-white/80">
            <input
              type="file"
              accept="video/mp4,video/quicktime"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <div>
              <div className="text-base text-white/80">Drop video · 15–180s</div>
              <div className="mt-1 text-xs text-white/30">mp4 · mov</div>
            </div>
          </label>
        )}

        {(busy || phase === 'done') && (
          <div className="flex flex-col gap-1.5 rounded-md border border-white/10 bg-black/30 p-3">
            <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.25em]">
              <span className={phase === 'done' ? 'text-emerald-300' : 'text-orange-300'}>
                {PHASE_LABEL[phase]}
              </span>
              <span className="text-white/40">{Math.round(progress * 100)}%</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/5">
              <div
                className={
                  'h-full rounded-full transition-[width] duration-200 ' +
                  (phase === 'done'
                    ? 'bg-emerald-400/80'
                    : 'bg-gradient-to-r from-orange-400 to-orange-300')
                }
                style={{ width: `${Math.max(2, progress * 100).toFixed(1)}%` }}
              />
            </div>
          </div>
        )}

        {analyzed && (
          <EngagementTimeline
            curves={engagementCurves}
            coldZones={coldZones}
            durationS={durationS}
            currentTime={currentTime}
            onPickColdZone={handlePickColdZone}
          />
        )}

        {analyzed && suggestions.length > 0 && (
          <div className="flex flex-col gap-2 rounded-md border border-white/10 bg-black/30 p-3">
            <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.25em] text-white/40">
              <span>brain feedback</span>
              <span>{suggestions.length} dip{suggestions.length === 1 ? '' : 's'}</span>
            </div>
            <ul className="flex flex-col gap-2">
              {suggestions.map((s) => (
                <li
                  key={s.id}
                  className="cursor-pointer rounded border border-white/5 bg-white/[0.02] px-3 py-2 text-xs text-white/80 transition-colors hover:border-orange-400/40 hover:bg-orange-400/5"
                  onClick={() => handlePickColdZone(s.cold_zone)}
                >
                  <div className="text-[10px] uppercase tracking-[0.2em] text-orange-300/80">
                    {s.cold_zone.start.toFixed(1)}s – {s.cold_zone.end.toFixed(1)}s · {s.cold_zone.region}
                  </div>
                  <div className="mt-1 leading-snug">{s.rationale}</div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {status === 'complete' && jobId && (
          <SimilarityPanel
            jobId={jobId}
            creatorId={DEMO_CREATOR_ID}
            refreshKey={librarySize ?? 0}
          />
        )}

        <LibraryUploader creatorId={DEMO_CREATOR_ID} onLibraryChange={setLibrarySize} />
      </div>

      <div className="flex shrink-0 items-center justify-between text-xs text-white/50">
        <div className="flex items-center gap-3">
          <span>{file ? file.name : 'no file selected'}</span>
          {fileTooLong && <span className="text-red-400">clip exceeds {TUNING.MAX_MEDIA_SECONDS}s</span>}
          {status === 'streaming' && <span className="text-orange-300">streaming…</span>}
          {status === 'complete' && (
            <span className="text-emerald-300">
              complete · click a red band to jump
            </span>
          )}
          {errorMessage && <span className="text-red-400">{errorMessage}</span>}
        </div>
        <div className="flex gap-2">
          {videoSrc && (
            <button
              type="button"
              onClick={() => {
                unsubRef.current?.();
                setFile(null);
                setVideoSrc(null);
                setClipId(null);
                resetAnalysis();
                frameBus.reset();
              }}
              disabled={busy}
              className="rounded-full border border-white/15 px-4 py-2 text-xs font-medium uppercase tracking-[0.2em] text-white/60 transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
            >
              clear
            </button>
          )}
          <button
            type="button"
            onClick={handleDiagnose}
            disabled={!file || busy || fileTooLong}
            className="rounded-full border border-orange-400/60 bg-orange-400/10 px-5 py-2 text-xs font-medium uppercase tracking-[0.2em] text-orange-200 transition-colors hover:bg-orange-400/20 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-transparent disabled:text-white/30"
          >
            {busy ? 'analyzing…' : 'Diagnose'}
          </button>
        </div>
      </div>
    </div>
  );
}
