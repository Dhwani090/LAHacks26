---
name: niivue-rendering
description: Patterns for using @niivue/niivue and niivue-react to render the cortical surface in Cortex. Load this skill when working on BrainMonitor.tsx, the colormap, frame interpolation, or any 3D brain visualization code. Niivue is a niche WebGL library — Claude's training coverage is shallow.
---

# Niivue Rendering Skill

## When to load this skill
Any task that:
- Imports from `@niivue/niivue` or `niivue-react`
- Touches `cortex/web/app/components/BrainMonitor.tsx`
- Touches `cortex/web/app/lib/colormap.ts`
- Renders meshes, applies vertex colors, or handles WebGL canvas state
- Animates between brain frames

## Canonical setup

```typescript
'use client';
import { Niivue } from '@niivue/niivue';
import { useEffect, useRef } from 'react';

export function BrainMonitor() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nvRef = useRef<Niivue | null>(null);

  useEffect(() => {
    const nv = new Niivue({
      backColor: [0.04, 0.04, 0.07, 1],  // dark navy
      show3Dcrosshair: false,
      isOrientCube: false,
      meshThicknessOn2D: 0,
    });
    nvRef.current = nv;

    nv.attachToCanvas(canvasRef.current!);

    // Load fsaverage5 mesh — left + right hemispheres
    nv.loadMeshes([
      { url: 'https://niivue.github.io/niivue-demo-images/BrainMesh_ICBM152.lh.mz3' },
      { url: 'https://niivue.github.io/niivue-demo-images/BrainMesh_ICBM152.rh.mz3' },
    ]);

    return () => {
      // cleanup
    };
  }, []);

  return <canvas ref={canvasRef} className="w-full h-full" />;
}
```

For the demo, use the ICBM152 placeholder mesh. For final, swap to actual fsaverage5 (~20k vertices, matches TRIBE's output).

## Vertex coloring (the activation rendering)

TRIBE outputs `Float32Array(20484)` per frame. Map to vertex colors:

```typescript
function applyActivation(nv: Niivue, activation: Float32Array) {
  // Map z-scores to RGBA colors via colormap
  const colors = new Uint8Array(activation.length * 4);
  for (let i = 0; i < activation.length; i++) {
    const [r, g, b, a] = zScoreToRGBA(activation[i]);
    colors[i * 4] = r;
    colors[i * 4 + 1] = g;
    colors[i * 4 + 2] = b;
    colors[i * 4 + 3] = a;
  }
  // Niivue mesh layer API:
  nv.meshes[0].layers[0].colormapValues = colors;
  nv.updateGLVolume();
}
```

The mesh layer API is the load-bearing call. If `nv.meshes[0].layers[0]` is undefined on first run, you need to call `nv.addMeshLayer(0, options)` first to create a layer slot.

## Colormap (cortex/web/app/lib/colormap.ts)

```typescript
const STOPS = [
  { z: -2,  rgba: [13, 26, 70, 255] },     // deep blue
  { z: -1,  rgba: [26, 58, 138, 255] },    // blue
  { z: 0,   rgba: [90, 112, 144, 255] },   // gray-blue
  { z: 1,   rgba: [232, 123, 30, 255] },   // orange
  { z: 2,   rgba: [255, 85, 0, 255] },     // bright orange (with glow)
];

export function zScoreToRGBA(z: number): [number, number, number, number] {
  // Linear interpolate between stops
  if (z <= STOPS[0].z) return STOPS[0].rgba as [number, number, number, number];
  if (z >= STOPS[STOPS.length - 1].z) return STOPS[STOPS.length - 1].rgba as [number, number, number, number];

  for (let i = 0; i < STOPS.length - 1; i++) {
    if (z >= STOPS[i].z && z < STOPS[i + 1].z) {
      const t = (z - STOPS[i].z) / (STOPS[i + 1].z - STOPS[i].z);
      return [
        Math.round(STOPS[i].rgba[0] + t * (STOPS[i + 1].rgba[0] - STOPS[i].rgba[0])),
        Math.round(STOPS[i].rgba[1] + t * (STOPS[i + 1].rgba[1] - STOPS[i].rgba[1])),
        Math.round(STOPS[i].rgba[2] + t * (STOPS[i + 1].rgba[2] - STOPS[i].rgba[2])),
        255,
      ];
    }
  }
  return [0, 0, 0, 255];
}
```

Don't use a built-in Niivue colormap — they're for medical imaging conventions, not branded UI. Custom is faster and looks better.

## Frame interpolation (1Hz → 30fps)

TRIBE outputs at 1 Hz. Browser renders at 60Hz. Interpolate per-vertex linearly between consecutive TRIBE frames using `requestAnimationFrame`:

```typescript
function startInterpolation(frames: Float32Array[], fps = 30) {
  let frameIdx = 0;
  const startTime = performance.now();
  const frameDurationMs = 1000;  // 1Hz TRIBE = 1s per frame

  function tick() {
    const elapsed = performance.now() - startTime;
    const exactFrame = elapsed / frameDurationMs;
    const i0 = Math.floor(exactFrame);
    const i1 = Math.min(i0 + 1, frames.length - 1);
    const t = exactFrame - i0;

    // Linear interpolation per vertex
    const interpolated = new Float32Array(20484);
    for (let v = 0; v < 20484; v++) {
      interpolated[v] = frames[i0][v] * (1 - t) + frames[i1][v] * t;
    }

    applyActivation(nv, interpolated);

    if (i0 < frames.length - 1) {
      requestAnimationFrame(tick);
    }
  }

  requestAnimationFrame(tick);
}
```

Apply a one-euro filter on top of this if jitter shows up — TRIBE prediction noise floor is real.

## Idle animation (the booth-pull)

Before any judge interacts, the brain should already be alive. Pre-render a "breathing" sequence:

```typescript
function startIdleAnimation() {
  const t0 = performance.now();
  function tick() {
    const t = (performance.now() - t0) / 1000;
    // Breathing: slow sine wave on baseline activation
    const phase = Math.sin(t * 0.5) * 0.3;  // ±0.3 z over ~12s period
    const baseline = new Float32Array(20484).fill(phase);
    applyActivation(nv, baseline);
    // Slow rotate
    nv.scene.renderAzimuth = (nv.scene.renderAzimuth + 0.05) % 360;
    nv.drawScene();
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}
```

Stop this when an analysis starts.

## Glow effect (P3-04 polish)

Niivue doesn't expose a glow shader directly. Two options:

1. **Cheap and good enough:** boost the alpha and saturation for high-z vertices in the colormap. Already in the STOPS above (255 alpha at z=2).

2. **Real glow:** custom shader. Niivue lets you inject GLSL via `nv.setMeshShader(meshIdx, shaderSource)`. Only do this if hour-budget allows. Look at https://niivue.com/docs/webgl/ for shader injection examples.

For a hackathon, option 1 is the right call.

## Camera + viewport

```typescript
nv.setMeshThicknessOn2D(0);
nv.setRenderAzimuthElevation(120, 15);  // 3D angle
nv.opts.dragMode = 0;  // disable drag during demo
nv.scene.clipPlane = [0, 0, 0, 0];  // no clipping
```

For the auto-rotate during idle, increment `nv.scene.renderAzimuth` per frame.

## Common gotchas

1. **`nv.attachToCanvas` is async-ish.** Wait until after `useEffect` mount before calling `loadMeshes`.

2. **`updateGLVolume()` must be called after every color change** or the canvas won't repaint.

3. **Don't recreate `Niivue` instance on re-render.** Use a ref. Recreating leaks WebGL contexts (Chrome caps at 16).

4. **`Float32Array` not regular array.** Niivue expects typed arrays for vertex data. Wrap incoming JSON arrays:
   ```typescript
   const activation = new Float32Array(jsonFrame.activation);
   ```

5. **Mesh load is slow first time** (~2-5s for fsaverage). Show a loading state. After first load, browser caches it.

## Reference
- https://niivue.com/docs/ — official docs
- https://github.com/niivue/niivue — source
- https://github.com/niivue/niivue-react — React bindings
- https://niivue.github.io/niivue/devdocs/ — API reference

If a Niivue method isn't in these docs, **don't invent it**. Ask the human or pick a different approach.
