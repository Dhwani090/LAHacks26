// Colormap — activation → RGBA on a neutral-gray cortex.
// PRD §10 (brain visualization).
// Style: medical fMRI heatmap. Inactive cortex stays gray (looks like an
// anatomical mesh); only above-threshold regions get warm color, lerping
// gray → red → yellow as intensity rises. Below threshold = no overlay.
// See .claude/skills/niivue-rendering/SKILL.md.

type RGBA = [number, number, number, number];

const BASE_GRAY: RGBA = [150, 150, 152, 255];

// Hot stops parameterized by `t ∈ [0, 1]` where t = 0 is the activation threshold
// and t = 1 is peak. Fades from gray-ish dark red into bright yellow.
const HOT_STOPS: { t: number; rgba: RGBA }[] = [
  { t: 0.0, rgba: [150, 150, 152, 255] },
  { t: 0.15, rgba: [140, 60, 60, 255] },
  { t: 0.4, rgba: [200, 40, 40, 255] },
  { t: 0.7, rgba: [240, 90, 30, 255] },
  { t: 1.0, rgba: [255, 230, 80, 255] },
];

function lerpStops(t: number): RGBA {
  const stops = HOT_STOPS;
  if (t <= stops[0].t) return stops[0].rgba;
  if (t >= stops[stops.length - 1].t) return stops[stops.length - 1].rgba;
  for (let i = 0; i < stops.length - 1; i++) {
    const a = stops[i];
    const b = stops[i + 1];
    if (t >= a.t && t <= b.t) {
      const u = (t - a.t) / (b.t - a.t);
      return [
        Math.round(a.rgba[0] + u * (b.rgba[0] - a.rgba[0])),
        Math.round(a.rgba[1] + u * (b.rgba[1] - a.rgba[1])),
        Math.round(a.rgba[2] + u * (b.rgba[2] - a.rgba[2])),
        255,
      ];
    }
  }
  return BASE_GRAY;
}

// Quickselect-style percentile so we don't sort 20k+ floats every frame.
function percentile(values: ArrayLike<number>, p: number): number {
  const n = values.length;
  if (n === 0) return 0;
  // For demo-scale arrays (≤ 20484), Array.sort is fast enough — but we copy
  // first so we don't reorder the input.
  const buf = new Float32Array(n);
  for (let i = 0; i < n; i++) buf[i] = values[i];
  buf.sort();
  const idx = Math.min(n - 1, Math.max(0, Math.floor(p * (n - 1))));
  return buf[idx];
}

/**
 * Map a per-vertex activation array to RGBA bytes for niivue.
 *
 * Below the per-frame `pLo` percentile → BASE_GRAY (no overlay).
 * Between `pLo` and `pHi` → gray → red → yellow lerp.
 * Above `pHi` → peak yellow.
 *
 * This produces the medical-style heatmap (gray cortex, red/yellow hotspots)
 * instead of painting every vertex on a blue↔orange axis.
 */
export function activationToVertexColors(
  activation: ArrayLike<number>,
  opts?: { pLo?: number; pHi?: number },
): Uint8Array {
  const pLo = opts?.pLo ?? 0.82;
  const pHi = opts?.pHi ?? 0.985;
  const n = activation.length;
  const out = new Uint8Array(n * 4);
  if (n === 0) return out;

  const lo = percentile(activation, pLo);
  const hi = percentile(activation, pHi);
  const span = Math.max(1e-6, hi - lo);

  for (let i = 0; i < n; i++) {
    const v = activation[i];
    const o = i * 4;
    if (v <= lo) {
      out[o] = BASE_GRAY[0];
      out[o + 1] = BASE_GRAY[1];
      out[o + 2] = BASE_GRAY[2];
      out[o + 3] = 255;
      continue;
    }
    const t = Math.min(1, (v - lo) / span);
    const [r, g, b] = lerpStops(t);
    out[o] = r;
    out[o + 1] = g;
    out[o + 2] = b;
    out[o + 3] = 255;
  }
  return out;
}

// Kept for external callers (timeline glow color, etc.). Maps a single z-score
// to the heatmap ramp with a fixed [0, 1.5] range.
export function zScoreToRGBA(z: number): RGBA {
  if (z <= 0) return BASE_GRAY;
  return lerpStops(Math.min(1, z / 1.5));
}
