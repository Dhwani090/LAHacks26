// /predict — upload a draft, watch the brain, click "Predict Engagement"
// after TRIBE finishes to fetch the predicted rate + percentile.
// PRD §6 (three modes) + §7 + §11.1.
// Wraps existing surfaces so text/audio modes still work; engagement card +
// similarity panel are video-mode-only and only appear after `complete`.
// See docs/PRD.md §6.3.
'use client';

import { AppShell } from '../components/AppShell';
import { ModeTabs } from '../components/ModeTabs';
import { TextSurface } from '../components/TextSurface';
import { AudioSurface } from '../components/AudioSurface';
import { VideoSurface } from '../components/VideoSurface';
import { useAppState } from '../state/AppState';

const SURFACES = {
  text: TextSurface,
  audio: AudioSurface,
  video: VideoSurface,
};

export default function PredictPage() {
  const mode = useAppState((s) => s.mode);
  const Surface = SURFACES[mode];

  return (
    <AppShell subtitle="upload a draft, watch the brain, predict engagement">
      <div className="flex min-h-0 flex-col gap-6">
        <ModeTabs />
        <div className="flex min-h-0 flex-1 flex-col">
          <Surface />
        </div>
      </div>
    </AppShell>
  );
}
