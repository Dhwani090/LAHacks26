// Cortex root page — split layout for P0-B.
// Implements PRD §3 (architecture) + §7 (frontend modules) shell.
// Left pane: ModeTabs + active surface. Right pane: BrainMonitor.
// Surfaces are placeholders; analysis wiring lands in P1+.
// See docs/PRD.md §6, §7.
'use client';

import { BrainMonitor } from './components/BrainMonitor';
import { ModeTabs } from './components/ModeTabs';
import { StatusChip } from './components/StatusChip';
import { TextSurface } from './components/TextSurface';
import { AudioSurface } from './components/AudioSurface';
import { VideoSurface } from './components/VideoSurface';
import { useAppState } from './state/AppState';

const SURFACES = {
  text: TextSurface,
  audio: AudioSurface,
  video: VideoSurface,
};

export default function Home() {
  const mode = useAppState((s) => s.mode);
  const Surface = SURFACES[mode];

  return (
    <main className="relative flex h-screen w-screen overflow-hidden bg-[#0a0a12] text-white">
      <section className="flex min-w-0 flex-1 flex-col gap-6 px-8 py-7">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-sm font-medium uppercase tracking-[0.3em] text-white/70">
              Cortex
            </h1>
            <p className="mt-1 text-xs text-white/40">
              predict what the average viewer&apos;s brain did with your work
            </p>
          </div>
          <StatusChip />
        </header>

        <ModeTabs />

        <div className="flex min-h-0 flex-1 flex-col">
          <Surface />
        </div>
      </section>

      <aside className="relative w-[42%] min-w-[420px] border-l border-white/10 bg-black/40">
        <BrainMonitor />
        <div className="pointer-events-none absolute bottom-4 right-5 text-[10px] uppercase tracking-[0.25em] text-white/30">
          fsaverage5 · z-scored BOLD
        </div>
      </aside>
    </main>
  );
}
