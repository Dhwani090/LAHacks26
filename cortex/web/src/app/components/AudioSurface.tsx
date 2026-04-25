// AudioSurface — drop-an-audio-clip UI for audio mode.
// PRD §6.2 (audio mode) + §7 — waveform and 2-track timeline arrive in P3-02.
// P0-B placeholder: file dropzone + filename display.
// Wires to /analyze/audio in P3-01.
// See docs/PRD.md §6.2.
'use client';

import { useState } from 'react';

export function AudioSurface() {
  const [file, setFile] = useState<File | null>(null);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <label
        className="flex min-h-0 flex-1 cursor-pointer items-center justify-center rounded-md border border-dashed border-white/15 bg-black/20 p-8 text-center text-sm text-white/50 transition-colors hover:border-orange-400/40 hover:text-white/80"
      >
        <input
          type="file"
          accept="audio/mpeg,audio/wav,audio/x-m4a,audio/mp4"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <div>
          <div className="text-base text-white/80">
            {file ? file.name : 'Drop audio · 15–60s'}
          </div>
          <div className="mt-1 text-xs text-white/30">mp3 · wav · m4a</div>
        </div>
      </label>
      <div className="flex shrink-0 items-center justify-between text-xs text-white/50">
        <span>{file ? `${Math.round(file.size / 1024)} KB` : 'no file selected'}</span>
        <button
          type="button"
          disabled={!file}
          className="rounded-full border border-orange-400/60 bg-orange-400/10 px-5 py-2 text-xs font-medium uppercase tracking-[0.2em] text-orange-200 transition-colors hover:bg-orange-400/20 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-transparent disabled:text-white/30"
        >
          Diagnose
        </button>
      </div>
    </div>
  );
}
