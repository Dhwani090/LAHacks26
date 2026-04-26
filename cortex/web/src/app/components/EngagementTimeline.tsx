// EngagementTimeline — per-track engagement curves under the video / audio.
// PRD §7.3 — 3 tracks for video (visual / auditory / language), 2 for audio.
// Each track is an SVG sparkline; cold zones overlay as red highlight bands.
// Click a cold zone → onPickColdZone callback (consumed by VideoSurface for jump-to).
// Pure presentational component; data comes from AppState (engagementCurves + coldZones).
'use client';

import { useMemo } from 'react';
import type { ColdZone, EngagementCurves } from '../lib/types';
import { TUNING } from '../lib/tuning';

interface Props {
  curves: EngagementCurves;
  coldZones: ColdZone[];
  durationS: number;
  currentTime?: number;
  onPickColdZone?: (zone: ColdZone) => void;
}

const TRACK_ORDER = ['visual', 'auditory', 'language'] as const;

const TRACK_COLOR: Record<string, { stroke: string; fill: string; label: string }> = {
  visual: { stroke: '#a78bfa', fill: 'rgba(167, 139, 250, 0.15)', label: 'visual cortex' },
  auditory: { stroke: '#34d399', fill: 'rgba(52, 211, 153, 0.15)', label: 'auditory cortex' },
  language: { stroke: '#fb923c', fill: 'rgba(251, 146, 60, 0.15)', label: 'language network' },
};

const VIEW_W = 1000;
const TRACK_H = 40;
const TRACK_GAP = 6;

// Per-track auto-scale: TRIBE returns z-scores with very small per-clip variance
// (~0.05 std), so a fixed [-1.5, 1.5] window made every line look flat. We scale
// to the curve's own range with a small floor so noise on a near-constant track
// doesn't get amplified into fake drama.
function scaleBounds(values: number[]): { lo: number; hi: number } {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of values) {
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return { lo: -1, hi: 1 };
  const span = hi - lo;
  const minSpan = 0.05;
  if (span < minSpan) {
    const mid = (lo + hi) / 2;
    return { lo: mid - minSpan / 2, hi: mid + minSpan / 2 };
  }
  const pad = span * 0.1;
  return { lo: lo - pad, hi: hi + pad };
}

function buildPath(values: number[], w: number, h: number): string {
  if (!values.length) return '';
  const { lo, hi } = scaleBounds(values);
  const yScale = (v: number) => h - ((v - lo) / (hi - lo)) * h;
  const xStep = w / Math.max(1, values.length - 1);
  let d = `M0 ${yScale(values[0]).toFixed(2)}`;
  for (let i = 1; i < values.length; i++) {
    d += ` L${(i * xStep).toFixed(2)} ${yScale(values[i]).toFixed(2)}`;
  }
  return d;
}

function buildArea(values: number[], w: number, h: number): string {
  const path = buildPath(values, w, h);
  if (!path) return '';
  return `${path} L${w.toFixed(2)} ${h} L0 ${h} Z`;
}

export function EngagementTimeline({
  curves,
  coldZones,
  durationS,
  currentTime,
  onPickColdZone,
}: Props) {
  const tracks = useMemo(
    () => TRACK_ORDER.filter((name) => Array.isArray(curves[name]) && curves[name].length > 0),
    [curves],
  );

  const empty = tracks.length === 0;
  const totalH = empty ? TRACK_H : tracks.length * TRACK_H + (tracks.length - 1) * TRACK_GAP;
  const safeDuration = durationS > 0 ? durationS : 1;

  return (
    <div className="flex flex-col gap-1 rounded-md border border-white/10 bg-black/30 p-3">
      <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.25em] text-white/40">
        <span>engagement timeline</span>
        <span>{durationS > 0 ? `${durationS.toFixed(0)}s` : '—'}</span>
      </div>

      <svg
        viewBox={`0 0 ${VIEW_W} ${totalH}`}
        preserveAspectRatio="none"
        className="h-[140px] w-full"
      >
        {empty ? (
          <text
            x={VIEW_W / 2}
            y={totalH / 2}
            textAnchor="middle"
            className="fill-white/30 text-xs"
          >
            waiting for engagement data…
          </text>
        ) : (
          <>
            {tracks.map((name, i) => {
              const values = curves[name];
              const yOffset = i * (TRACK_H + TRACK_GAP);
              const color = TRACK_COLOR[name];
              return (
                <g key={name} transform={`translate(0 ${yOffset})`}>
                  <rect
                    x={0}
                    y={0}
                    width={VIEW_W}
                    height={TRACK_H}
                    className="fill-white/[0.02]"
                  />
                  <line
                    x1={0}
                    x2={VIEW_W}
                    y1={TRACK_H / 2}
                    y2={TRACK_H / 2}
                    className="stroke-white/10"
                    strokeDasharray="2 4"
                  />
                  <path d={buildArea(values, VIEW_W, TRACK_H)} fill={color.fill} />
                  <path
                    d={buildPath(values, VIEW_W, TRACK_H)}
                    fill="none"
                    stroke={color.stroke}
                    strokeWidth={1.5}
                  />
                </g>
              );
            })}

            {coldZones.map((z, i) => {
              const x = (z.start / safeDuration) * VIEW_W;
              const w = Math.max(2, ((z.end - z.start) / safeDuration) * VIEW_W);
              const interactive = !!onPickColdZone;
              return (
                <rect
                  key={`zone-${i}`}
                  x={x}
                  y={0}
                  width={w}
                  height={totalH}
                  fill="rgba(248, 113, 113, 0.18)"
                  stroke="rgba(248, 113, 113, 0.6)"
                  strokeWidth={1}
                  style={{
                    cursor: interactive ? 'pointer' : 'default',
                    opacity: TUNING.COLD_HIGHLIGHT_OPACITY + 0.2,
                  }}
                  onClick={interactive ? () => onPickColdZone!(z) : undefined}
                />
              );
            })}

            {currentTime !== undefined && currentTime >= 0 && (
              <line
                x1={(currentTime / safeDuration) * VIEW_W}
                x2={(currentTime / safeDuration) * VIEW_W}
                y1={0}
                y2={totalH}
                stroke="rgba(255, 255, 255, 0.7)"
                strokeWidth={1.5}
              />
            )}
          </>
        )}
      </svg>

      {!empty && (
        <div className="flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-[0.2em] text-white/40">
          {tracks.map((name) => (
            <span key={name} className="flex items-center gap-1.5">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: TRACK_COLOR[name].stroke }}
              />
              {TRACK_COLOR[name].label}
            </span>
          ))}
          {coldZones.length > 0 && (
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-sm bg-red-400/60" />
              cold zone
            </span>
          )}
        </div>
      )}
    </div>
  );
}
