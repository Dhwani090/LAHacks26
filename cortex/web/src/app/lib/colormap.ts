// Colormap — z-score → RGBA, used to color fsaverage5 vertices.
// PRD §10 (brain visualization) + skills/niivue-rendering/SKILL.md.
// Custom branded gradient; do NOT swap to a built-in Niivue medical colormap.
// Linear interpolation between stops; clamps outside [-2, 2].
// See .claude/skills/niivue-rendering/SKILL.md.

type RGBA = [number, number, number, number];

interface Stop {
  z: number;
  rgba: RGBA;
}

const STOPS: Stop[] = [
  { z: -2, rgba: [13, 26, 70, 255] },
  { z: -1, rgba: [26, 58, 138, 255] },
  { z: 0, rgba: [90, 112, 144, 255] },
  { z: 1, rgba: [232, 123, 30, 255] },
  { z: 2, rgba: [255, 110, 30, 255] },
  { z: 3, rgba: [255, 220, 170, 255] },
];

export function zScoreToRGBA(z: number): RGBA {
  if (z <= STOPS[0].z) return STOPS[0].rgba;
  if (z >= STOPS[STOPS.length - 1].z) return STOPS[STOPS.length - 1].rgba;

  for (let i = 0; i < STOPS.length - 1; i++) {
    const a = STOPS[i];
    const b = STOPS[i + 1];
    if (z >= a.z && z < b.z) {
      const t = (z - a.z) / (b.z - a.z);
      return [
        Math.round(a.rgba[0] + t * (b.rgba[0] - a.rgba[0])),
        Math.round(a.rgba[1] + t * (b.rgba[1] - a.rgba[1])),
        Math.round(a.rgba[2] + t * (b.rgba[2] - a.rgba[2])),
        255,
      ];
    }
  }
  return [0, 0, 0, 255];
}

export function activationToVertexColors(activation: ArrayLike<number>): Uint8Array {
  const out = new Uint8Array(activation.length * 4);
  for (let i = 0; i < activation.length; i++) {
    const [r, g, b, a] = zScoreToRGBA(activation[i]);
    const o = i * 4;
    out[o] = r;
    out[o + 1] = g;
    out[o + 2] = b;
    out[o + 3] = a;
  }
  return out;
}
