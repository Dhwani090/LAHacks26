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

export function VideoSurface() {
  const [file, setFile] = useState<File | null>(null);
  const [videoSrc, setVideoSrc] = useState<string | null>(null);
  const [, setClipId] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);

  const status = useAppState((s) => s.status);
  const errorMessage = useAppState((s) => s.errorMessage);
  const coldZones = useAppState((s) => s.coldZones);
  const engagementCurves = useAppState((s) => s.engagementCurves);
  const durationS = useAppState((s) => s.durationS);
  const jobId = useAppState((s) => s.jobId);
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

  function handleDiagnose() {
    if (!file || busy) return;

    unsubRef.current?.();
    resetAnalysis();
    frameBus.reset();
    setStatus('submitting');

    brainClient
      .analyzeVideo(file)
      .then((job) => {
        setJobId(job.job_id);
        setClipId(job.job_id);
        setStatus('streaming');

        unsubRef.current = subscribeAnalysis(brainClient.streamUrl(job.job_id), {
          onTranscript: (words: TranscriptWord[]) => setTranscript(words),
          onBrainFrame: (frame) => frameBus.publish(frame),
          onColdZones: (zones: ColdZone[]) => setColdZones(zones),
          onSuggestions: (items) => setSuggestions(items),
          onComplete: (payload) => {
            const curves = payload?.engagement_curves as EngagementCurves | undefined;
            const dur = payload?.duration_s as number | undefined;
            if (curves) setEngagementCurves(curves);
            if (typeof dur === 'number') setDurationS(dur);
            setStatus('complete');
          },
          onError: (err) => {
            console.error('[VideoSurface] stream error', err);
            setError('stream error — backend may be down');
          },
        });
      })
      .catch((err) => {
        console.error('[VideoSurface] analyze failed', err);
        setError(err instanceof Error ? err.message : 'analyze failed');
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

        {analyzed && (
          <EngagementTimeline
            curves={engagementCurves}
            coldZones={coldZones}
            durationS={durationS}
            currentTime={currentTime}
            onPickColdZone={handlePickColdZone}
          />
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
