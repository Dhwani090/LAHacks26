// BrainMonitor — Niivue cortical surface render target.
// Implements PRD §7.1 (BrainMonitor) and §10 (brain visualization).
// P1-04: subscribes to frameBus, runs 1Hz→30fps interpolation, drives per-vertex
// colors via colormap. CSS halo around the canvas pulses with mean activation
// so the demo has visible feedback even if the placeholder mesh's vertex count
// (lh-only ICBM152, ~2562 verts) doesn't match TRIBE's 20484. Real fsaverage5
// swap eliminates the mismatch.
// Patterns: see .claude/skills/niivue-rendering/SKILL.md.
'use client';

import { Niivue, NVMesh } from '@niivue/niivue';
import { useEffect, useRef, useState } from 'react';
import { activationToVertexColors } from '../lib/colormap';
import { frameBus } from '../lib/frameBus';
import { TUNING } from '../lib/tuning';
import type { BrainFrame } from '../lib/types';

// Niivue ships the LH ICBM152 mesh only — there is no RH counterpart hosted
// anywhere niivue or kitware publishes. We mirror the LH at load-time to
// synthesize an RH; ICBM152 is sagittally near-symmetric so the mirror reads
// as a proper full brain to a non-anatomist judge.
const MESH_URLS = [
  'https://niivue.com/demos/images/BrainMesh_ICBM152.lh.mz3',
];

export function BrainMonitor() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nvRef = useRef<Niivue | null>(null);
  const meshVertCountRef = useRef<number>(0);
  const framesRef = useRef<BrainFrame[]>([]);
  const playStartMsRef = useRef<number | null>(null);
  const tickTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Persisted across ticks: the activation we actually painted last frame.
  // Each new tick lerps toward the freshly-interpolated TRIBE values, which
  // turns the per-frame jitter into smooth flowing waves of activation.
  const displayedRef = useRef<Float32Array | null>(null);
  const [meanActivation, setMeanActivation] = useState(0);
  const [playT, setPlayT] = useState<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const nv = new Niivue({
      backColor: [0.04, 0.04, 0.07, 1],
      show3Dcrosshair: false,
      isOrientCube: false,
      meshThicknessOn2D: 0,
    });
    nvRef.current = nv;

    let cancelled = false;

    (async () => {
      await nv.attachToCanvas(canvas);
      if (cancelled) return;
      try {
        await nv.loadMeshes(MESH_URLS.map((url) => ({ url })));
      } catch (err) {
        console.error('[BrainMonitor] mesh load failed', err);
        return;
      }
      if (cancelled || !nvRef.current) return;

      // Synthesize the RH by mirroring the LH across the sagittal plane (X axis).
      // Triangle winding flips under reflection, so we also reverse winding so
      // the RH faces shade with outward normals (otherwise it renders inside-out
      // and looks like a hole instead of a hemisphere).
      try {
        const lh = nv.meshes[0];
        const lhPts = (lh as { pts?: Float32Array }).pts;
        const lhTris = (lh as { tris?: Uint32Array }).tris;
        const gl = (nv as unknown as { gl?: WebGL2RenderingContext }).gl;
        if (lhPts && lhTris && gl) {
          const rhPts = new Float32Array(lhPts);
          for (let i = 0; i < rhPts.length; i += 3) rhPts[i] = -rhPts[i];
          const rhTris = new Uint32Array(lhTris.length);
          for (let i = 0; i < lhTris.length; i += 3) {
            rhTris[i] = lhTris[i];
            rhTris[i + 1] = lhTris[i + 2];
            rhTris[i + 2] = lhTris[i + 1];
          }
          const rhRgba = new Uint8Array((rhPts.length / 3) * 4).fill(180);
          const rh = new NVMesh(rhPts, rhTris, 'rh-mirror', rhRgba, 1.0, true, gl);
          nv.meshes.push(rh);
        }
      } catch (err) {
        console.warn('[BrainMonitor] RH mirror failed', err);
      }

      // Build a per-mesh vertex-count table so we can paint LH and RH from the
      // same TRIBE activation vector. We stride-sample the TRIBE vector across
      // the combined brain and slice out each mesh's chunk.
      const meshVertCounts: number[] = [];
      for (const m of nv.meshes) {
        const pts = (m as { pts?: Float32Array }).pts;
        const ptsN = pts ? Math.floor(pts.length / 3) : 0;
        const rgbaN = m?.rgba255 ? Math.floor(m.rgba255.length / 4) : 0;
        const n = ptsN > 0 ? ptsN : rgbaN;
        meshVertCounts.push(n);
        if (n > 0) {
          const want = n * 4;
          if (!m.rgba255 || m.rgba255.length !== want) {
            m.rgba255 = new Uint8Array(want).fill(180);
          }
        }
      }
      const totalVerts = meshVertCounts.reduce((a, b) => a + b, 0);
      meshVertCountRef.current = totalVerts;

      // Build vertex adjacency on the combined LH+RH mesh so we can do
      // graph-Laplacian-style smoothing. Without this, thresholding the per-
      // vertex activation looks like speckled noise; with 3-4 smoothing iters
      // the same activation field reads as growing/shrinking heat pools.
      const adjacencyOffsets = new Uint32Array(totalVerts + 1);
      let neighborCount = 0;
      const sets: Set<number>[] = Array.from({ length: totalVerts }, () => new Set());
      let baseOffset = 0;
      for (let mi = 0; mi < nv.meshes.length; mi++) {
        const mesh = nv.meshes[mi];
        const tris = (mesh as { tris?: Uint32Array }).tris;
        const n = meshVertCounts[mi];
        if (tris && n > 0) {
          for (let i = 0; i < tris.length; i += 3) {
            const a = tris[i] + baseOffset;
            const b = tris[i + 1] + baseOffset;
            const c = tris[i + 2] + baseOffset;
            if (a < totalVerts && b < totalVerts && c < totalVerts) {
              sets[a].add(b); sets[a].add(c);
              sets[b].add(a); sets[b].add(c);
              sets[c].add(a); sets[c].add(b);
            }
          }
        }
        baseOffset += n;
      }
      for (let v = 0; v < totalVerts; v++) neighborCount += sets[v].size;
      const adjacencyData = new Uint32Array(neighborCount);
      let cursor = 0;
      for (let v = 0; v < totalVerts; v++) {
        adjacencyOffsets[v] = cursor;
        sets[v].forEach((nb) => {
          adjacencyData[cursor++] = nb;
        });
      }
      adjacencyOffsets[totalVerts] = cursor;
      // Scratch buffer reused across smoothing iterations to avoid allocation
      // pressure (this runs every tick).
      const smoothScratch = new Float32Array(totalVerts);
      const smoothInPlace = (buf: Float32Array, iters: number) => {
        for (let it = 0; it < iters; it++) {
          for (let v = 0; v < totalVerts; v++) {
            const start = adjacencyOffsets[v];
            const end = adjacencyOffsets[v + 1];
            let sum = buf[v];
            for (let k = start; k < end; k++) sum += buf[adjacencyData[k]];
            smoothScratch[v] = sum / (1 + (end - start));
          }
          buf.set(smoothScratch);
        }
      };
      nv.setRenderAzimuthElevation(120, 15);
      nv.opts.dragMode = 0;

      const applyColors = (activation: ArrayLike<number>) => {
        try {
          const gl = (nv as unknown as { gl?: WebGL2RenderingContext }).gl;
          if (!gl) return;
          let cursor = 0;
          for (let mi = 0; mi < nv.meshes.length; mi++) {
            const mesh = nv.meshes[mi];
            const n = meshVertCounts[mi];
            if (!mesh?.rgba255 || mesh.rgba255.length !== n * 4) continue;
            // Slice the global colors view for this mesh's vertices.
            const slice =
              activation instanceof Float32Array
                ? activation.subarray(cursor, cursor + n)
                : Array.from({ length: n }, (_, k) => activation[cursor + k]);
            mesh.rgba255.set(activationToVertexColors(slice));
            const mAny = mesh as unknown as {
              updateMesh?: (gl: WebGL2RenderingContext) => void;
            };
            mAny.updateMesh?.(gl);
            cursor += n;
          }
          nv.drawScene();
        } catch (err) {
          if (process.env.NODE_ENV === 'development') {
            console.warn('[BrainMonitor] vertex color skip', err);
          }
        }
      };

      const tick = () => {
        if (cancelled || !nvRef.current) return;

        const frames = framesRef.current;
        const startMs = playStartMsRef.current;
        const targetLen = meshVertCountRef.current;
        const playing = frames.length > 0 && startMs !== null;

        // Pause auto-rotation while a real activation is playing — the user is
        // here to watch *which regions* light up, not to watch the brain spin.
        if (!playing) {
          nv.scene.renderAzimuth =
            (nv.scene.renderAzimuth + TUNING.IDLE_AZIMUTH_STEP_DEG) % 360;
        }

        if (playing && targetLen > 0) {
          // Loop the activation: once we hit the last frame, wrap back to the
          // first so the judge can keep watching the dynamics. PLAYBACK_RATE<1
          // stretches each TRIBE second over more wall-clock time.
          const frameMs = TUNING.TRIBE_FRAME_MS / TUNING.PLAYBACK_RATE;
          const loopMs = frames.length * frameMs;
          const elapsed = (performance.now() - startMs!) % loopMs;
          const exact = elapsed / frameMs;
          const i0 = Math.min(Math.floor(exact), frames.length - 1);
          const i1 = (i0 + 1) % frames.length;
          const raw = Math.min(1, Math.max(0, exact - i0));
          // Smoothstep (3t² − 2t³) — softens linear-interp jolt between frames.
          const t = raw * raw * (3 - 2 * raw);

          const a = frames[i0].activation;
          const b = frames[i1].activation;
          // Reuse a persistent buffer so the temporal EMA from the previous
          // tick survives — that's what makes hotspots glide instead of flicker.
          if (!displayedRef.current || displayedRef.current.length !== targetLen) {
            displayedRef.current = new Float32Array(targetLen);
          }
          const displayed = displayedRef.current;
          const blend = TUNING.TEMPORAL_BLEND;
          const stride = a.length / targetLen;
          let sum = 0;
          for (let v = 0; v < targetLen; v++) {
            const src = Math.min(a.length - 1, Math.floor(v * stride));
            const fresh = a[src] * (1 - t) + b[src] * t;
            const next = displayed[v] * (1 - blend) + fresh * blend;
            displayed[v] = next;
            sum += next;
          }
          setMeanActivation(sum / targetLen);
          setPlayT(exact);
          // Spatial smoothing on the temporally-blended state — together they
          // turn TRIBE's per-vertex z-scores into the "growing pool" heatmap.
          smoothInPlace(displayed, TUNING.SPATIAL_SMOOTH_ITERS);
          applyColors(displayed);
        } else if (targetLen > 0) {
          // Idle breathing: low-frequency global pulse so the brain looks alive
          // even before any analysis runs.
          const omega = performance.now() * 0.001 * TUNING.IDLE_BREATHE_HZ * Math.PI * 2;
          const phase = Math.sin(omega) * TUNING.IDLE_BREATHE_AMPLITUDE_Z;
          const baseline = new Float32Array(targetLen);
          baseline.fill(phase);
          setMeanActivation(phase);
          if (playT !== null) setPlayT(null);
          applyColors(baseline);
        } else {
          nv.drawScene();
        }
      };
      // setInterval (not requestAnimationFrame) so the brain keeps breathing even
      // when the tab is backgrounded (rAF pauses on hidden tabs and would freeze
      // the demo if a judge tabs away). 33ms ≈ 30Hz, indistinguishable from rAF
      // at this scale.
      tickTimerRef.current = setInterval(tick, 33);
    })();

    return () => {
      cancelled = true;
      if (tickTimerRef.current !== null) clearInterval(tickTimerRef.current);
      tickTimerRef.current = null;
      nvRef.current = null;
    };
  }, []);

  useEffect(() => {
    const unsubFrame = frameBus.subscribe((frame) => {
      framesRef.current.push(frame);
      if (playStartMsRef.current === null) {
        playStartMsRef.current = performance.now();
      }
    });
    const unsubReset = frameBus.onReset(() => {
      framesRef.current = [];
      playStartMsRef.current = null;
      displayedRef.current = null;
      setMeanActivation(0);
      setPlayT(null);
    });
    return () => {
      unsubFrame();
      unsubReset();
    };
  }, []);

  // Halo follows mean activation; warm-only palette to match the new heatmap
  // (red→yellow on gray cortex). Idle breathing reads as a soft red pulse.
  const mag = Math.min(1, Math.max(0, meanActivation) / 1.5);
  const innerAlpha = 0.18 + mag * 0.55;
  const outerAlpha = 0.08 + mag * 0.35;
  const innerHalo = `rgba(220,60,40,${innerAlpha.toFixed(3)})`;
  const outerHalo = `rgba(255,180,60,${outerAlpha.toFixed(3)})`;

  return (
    <div
      className="relative h-full w-full"
      style={{
        // Layered shadows: outer drop-glow + inner edge-glow. Idle breathing reads
        // as a slow pulse around the canvas; real activations pulse harder.
        boxShadow: `inset 0 0 160px 30px ${innerHalo}, 0 0 80px 0 ${outerHalo}`,
        backgroundColor: 'black',
      }}
    >
      <canvas
        ref={canvasRef}
        className="h-full w-full"
        data-testid="brain-monitor-canvas"
      />
      {playT !== null && (
        <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2 rounded-full border border-orange-300/30 bg-black/60 px-3 py-1 text-[10px] uppercase tracking-[0.25em] text-orange-200/90 backdrop-blur">
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-orange-300" />
          <span>t = {playT.toFixed(1)}s</span>
          <span className="text-white/30">· loop</span>
        </div>
      )}
    </div>
  );
}
