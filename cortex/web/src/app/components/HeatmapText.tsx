// HeatmapText — per-sentence engagement visualization for text mode.
// PRD §6.1 (text mode) + §7.2 (HeatmapText verification).
// Subscribes to frameBus; recomputes sentence scores as frames stream in.
// Sentences are mapped to proportional time slots over the analysis duration.
// Click a cold sentence → onPickColdSentence callback (P1-07 wires this).
'use client';

import { useEffect, useMemo, useState } from 'react';
import { frameBus } from '../lib/frameBus';
import { TUNING } from '../lib/tuning';

interface Props {
  text: string;
  onPickColdSentence?: (index: number, text: string) => void;
}

function splitSentences(text: string): string[] {
  // Keep the trailing punctuation+space with the sentence.
  return text
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function HeatmapText({ text, onPickColdSentence }: Props) {
  const sentences = useMemo(() => splitSentences(text), [text]);
  const [scores, setScores] = useState<number[]>(() => sentences.map(() => 0));

  useEffect(() => {
    const meanPerFrame: number[] = [];

    const recompute = () => {
      const total = meanPerFrame.length;
      if (total === 0) {
        setScores(sentences.map(() => 0));
        return;
      }
      const next = sentences.map((_, i) => {
        const start = Math.floor((i / sentences.length) * total);
        const end = Math.max(start + 1, Math.floor(((i + 1) / sentences.length) * total));
        const slice = meanPerFrame.slice(start, Math.min(end, total));
        if (!slice.length) return 0;
        return slice.reduce((a, b) => a + b, 0) / slice.length;
      });
      setScores(next);
    };

    const unsubFrame = frameBus.subscribe((f) => {
      const sum = f.activation.reduce((a, b) => a + b, 0);
      meanPerFrame.push(sum / f.activation.length);
      recompute();
    });
    const unsubReset = frameBus.onReset(() => {
      meanPerFrame.length = 0;
      setScores(sentences.map(() => 0));
    });

    return () => {
      unsubFrame();
      unsubReset();
    };
  }, [sentences]);

  return (
    <div className="overflow-y-auto rounded-md border border-white/10 bg-black/30 p-4 text-base leading-relaxed">
      {sentences.map((s, i) => {
        const score = scores[i] ?? 0;
        const cold = score < TUNING.COLD_THRESHOLD_Z;
        const hot = score > TUNING.HOT_THRESHOLD_Z;
        const colorClass = cold
          ? 'text-blue-200 decoration-blue-400 hover:bg-blue-400/10'
          : hot
            ? 'text-orange-200 decoration-orange-400'
            : 'text-white/80 decoration-white/15';
        const interactive = cold && onPickColdSentence;
        return (
          <span
            key={i}
            role={interactive ? 'button' : undefined}
            tabIndex={interactive ? 0 : undefined}
            onClick={
              interactive ? () => onPickColdSentence!(i, s) : undefined
            }
            className={`mr-1 underline decoration-2 underline-offset-4 transition-colors duration-300 ${colorClass} ${
              interactive ? 'cursor-pointer rounded px-0.5' : ''
            }`}
          >
            {s}
          </span>
        );
      })}
    </div>
  );
}
