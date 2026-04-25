// ModeTabs — Text / Audio / Video toggle.
// PRD §7 (frontend modules) — controls active mode, animated underline.
// Reads/writes Zustand AppState.mode. Switching mode resets analysis.
// framer-motion handles the active indicator slide.
// See docs/PRD.md §6 for mode definitions.
'use client';

import { motion } from 'framer-motion';
import { useAppState } from '../state/AppState';
import type { Mode } from '../lib/types';
import { TUNING } from '../lib/tuning';

const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: 'text', label: 'Text', hint: 'paste up to 500 words' },
  { id: 'audio', label: 'Audio', hint: '15–60s clip' },
  { id: 'video', label: 'Video', hint: '15–60s clip' },
];

export function ModeTabs() {
  const mode = useAppState((s) => s.mode);
  const setMode = useAppState((s) => s.setMode);

  return (
    <nav
      role="tablist"
      aria-label="Analysis mode"
      className="flex items-end gap-6 border-b border-white/10"
    >
      {MODES.map((m) => {
        const active = m.id === mode;
        return (
          <button
            key={m.id}
            role="tab"
            aria-selected={active}
            onClick={() => setMode(m.id)}
            className="relative flex flex-col items-start gap-1 pb-3 pt-1 text-left transition-colors"
          >
            <span
              className={`text-sm font-medium tracking-wide ${
                active ? 'text-white' : 'text-white/50 hover:text-white/80'
              }`}
            >
              {m.label}
            </span>
            <span
              className={`text-[10px] uppercase tracking-[0.18em] ${
                active ? 'text-white/60' : 'text-white/30'
              }`}
            >
              {m.hint}
            </span>
            {active && (
              <motion.span
                layoutId="mode-underline"
                className="absolute -bottom-px left-0 right-0 h-px bg-orange-400"
                transition={{
                  type: 'spring',
                  stiffness: 320,
                  damping: 30,
                  duration: TUNING.MODE_TRANSITION_MS / 1000,
                }}
              />
            )}
          </button>
        );
      })}
    </nav>
  );
}
