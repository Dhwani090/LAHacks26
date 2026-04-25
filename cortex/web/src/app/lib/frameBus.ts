// frameBus — module-level pub/sub for brain frames.
// Frames are 20484-float arrays; routing them through Zustand would re-render
// every subscriber on every frame. Producer pushes here; BrainMonitor subscribes.
// PRD §7.1 + skills/niivue-rendering/SKILL.md (frame interpolation patterns).
// See cortex/web/src/app/components/BrainMonitor.tsx.

import type { BrainFrame } from './types';

type Listener = (frame: BrainFrame) => void;
type ResetListener = () => void;

const frameListeners = new Set<Listener>();
const resetListeners = new Set<ResetListener>();

export const frameBus = {
  publish(frame: BrainFrame): void {
    frameListeners.forEach((l) => l(frame));
  },
  subscribe(fn: Listener): () => void {
    frameListeners.add(fn);
    return () => {
      frameListeners.delete(fn);
    };
  },
  reset(): void {
    resetListeners.forEach((l) => l());
  },
  onReset(fn: ResetListener): () => void {
    resetListeners.add(fn);
    return () => {
      resetListeners.delete(fn);
    };
  },
};
