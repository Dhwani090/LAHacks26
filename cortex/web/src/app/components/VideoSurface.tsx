// VideoSurface — drop-a-video-clip UI for video mode (the spectacle).
// PRD §6.3 (video mode) + §7 — player, 3-track timeline, auto-improve in P2.
// P0-B placeholder: file dropzone + preview + disabled Diagnose / Auto-improve.
// Wires to /analyze/video and /auto-improve in P2-01/02/06/07.
// See docs/PRD.md §6.3.
'use client';

import { useState } from 'react';

export function VideoSurface() {
  const [file, setFile] = useState<File | null>(null);
  const previewUrl = file ? URL.createObjectURL(file) : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <label className="flex min-h-0 flex-1 cursor-pointer flex-col items-center justify-center gap-3 rounded-md border border-dashed border-white/15 bg-black/20 p-6 text-center text-sm text-white/50 transition-colors hover:border-orange-400/40 hover:text-white/80">
        <input
          type="file"
          accept="video/mp4,video/quicktime"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        {previewUrl ? (
          <video
            src={previewUrl}
            controls
            className="h-full max-h-[280px] w-full rounded bg-black object-contain"
          />
        ) : (
          <div>
            <div className="text-base text-white/80">Drop video · 15–60s</div>
            <div className="mt-1 text-xs text-white/30">mp4 · mov</div>
          </div>
        )}
      </label>
      <div className="flex shrink-0 items-center justify-between text-xs text-white/50">
        <span>{file ? file.name : 'no file selected'}</span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={!file}
            className="rounded-full border border-orange-400/60 bg-orange-400/10 px-5 py-2 text-xs font-medium uppercase tracking-[0.2em] text-orange-200 transition-colors hover:bg-orange-400/20 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-transparent disabled:text-white/30"
          >
            Diagnose
          </button>
          <button
            type="button"
            disabled
            className="rounded-full border border-white/15 px-5 py-2 text-xs font-medium uppercase tracking-[0.2em] text-white/40 disabled:cursor-not-allowed"
          >
            Auto-improve
          </button>
        </div>
      </div>
    </div>
  );
}
