// BrainMonitor — Niivue cortical surface render target.
// Implements PRD §7.1 (BrainMonitor) and §10 (brain visualization).
// P1-04: subscribes to frameBus, runs 1Hz→30fps interpolation, drives per-vertex
// colors via colormap. CSS halo around the canvas pulses with mean activation
// so the demo has visible feedback even if the placeholder mesh's vertex count
// (lh-only ICBM152, ~2562 verts) doesn't match TRIBE's 20484. Real fsaverage5
// swap eliminates the mismatch.
// Patterns: see .claude/skills/niivue-rendering/SKILL.md.
'use client';

import { Niivue } from '@niivue/niivue';
import { useEffect, useRef, useState } from 'react';
import { activationToVertexColors } from '../lib/colormap';
import { frameBus } from '../lib/frameBus';
import { TUNING } from '../lib/tuning';
import type { BrainFrame } from '../lib/types';

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
  const [meanActivation, setMeanActivation] = useState(0);
  const [initError, setInitError] = useState<string | null>(null);

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
      try {
        await nv.attachToCanvas(canvas);
      } catch (err) {
        // Niivue throws synchronously inside attachToCanvas when WebGL2 isn't
        // available (headless browsers, ancient hardware, GPU blocklist).
        // Surface a soft fallback instead of letting an unhandled promise
        // rejection crash the page — the rest of the app works without the
        // brain visualization.
        const msg = err instanceof Error ? err.message : String(err);
        console.error('[BrainMonitor] WebGL2 init failed', err);
        if (!cancelled) setInitError(msg);
        return;
      }
      if (cancelled) return;
      try {
        await nv.loadMeshes(MESH_URLS.map((url) => ({ url })));
      } catch (err) {
        console.error('[BrainMonitor] mesh load failed', err);
        if (!cancelled) setInitError(err instanceof Error ? err.message : 'mesh load failed');
        return;
      }
      if (cancelled || !nvRef.current) return;

      const mesh = nv.meshes[0];
      // Prefer pts (vertex positions) — niivue's rgba255 may be a 1-vertex default
      // color rather than a per-vertex array, in which case it lies about vert count
      // and the breathing/playback loop sees targetLen=1 and never paints anything.
      const ptsCount = mesh?.pts ? Math.floor(mesh.pts.length / 3) : 0;
      const rgbaCount = mesh?.rgba255 ? Math.floor(mesh.rgba255.length / 4) : 0;
      meshVertCountRef.current = ptsCount > 0 ? ptsCount : rgbaCount;
      nv.setRenderAzimuthElevation(120, 15);
      nv.opts.dragMode = 0;

      const applyColors = (activation: ArrayLike<number>) => {
        try {
          const mesh = nv.meshes[0];
          const targetLen = meshVertCountRef.current;
          if (mesh?.rgba255 && mesh.rgba255.length === targetLen * 4) {
            mesh.rgba255.set(activationToVertexColors(activation));
            nv.updateGLVolume();
          }
        } catch (err) {
          if (process.env.NODE_ENV === 'development') {
            console.warn('[BrainMonitor] vertex color skip', err);
          }
        }
      };

      const tick = () => {
        if (cancelled || !nvRef.current) return;
        nv.scene.renderAzimuth =
          (nv.scene.renderAzimuth + TUNING.IDLE_AZIMUTH_STEP_DEG) % 360;

        const frames = framesRef.current;
        const startMs = playStartMsRef.current;
        const targetLen = meshVertCountRef.current;
        const playing = frames.length > 0 && startMs !== null;

        if (playing && targetLen > 0) {
          const elapsed = performance.now() - startMs!;
          const exact = elapsed / TUNING.TRIBE_FRAME_MS;
          const i0 = Math.min(Math.floor(exact), frames.length - 1);
          const i1 = Math.min(i0 + 1, frames.length - 1);
          const raw = Math.min(1, Math.max(0, exact - i0));
          // Smoothstep easing (3t² − 2t³) — kills the linear-interp jolt between frames.
          const t = raw * raw * (3 - 2 * raw);

          const a = frames[i0].activation;
          const b = frames[i1].activation;
          const interp = new Float32Array(targetLen);
          const stride = a.length / targetLen;
          let sum = 0;
          for (let v = 0; v < targetLen; v++) {
            const src = Math.min(a.length - 1, Math.floor(v * stride));
            const value = a[src] * (1 - t) + b[src] * t;
            interp[v] = value;
            sum += value;
          }
          setMeanActivation(sum / targetLen);
          applyColors(interp);

          if (
            i0 >= frames.length - 1 &&
            elapsed > frames.length * TUNING.TRIBE_FRAME_MS + 500
          ) {
            // Drain into idle breathing.
            framesRef.current = [];
            playStartMsRef.current = null;
          }
        } else if (targetLen > 0) {
          // Idle breathing: low-frequency global pulse so the brain looks alive
          // even before any analysis runs.
          const omega = performance.now() * 0.001 * TUNING.IDLE_BREATHE_HZ * Math.PI * 2;
          const phase = Math.sin(omega) * TUNING.IDLE_BREATHE_AMPLITUDE_Z;
          const baseline = new Float32Array(targetLen);
          baseline.fill(phase);
          setMeanActivation(phase);
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
      setMeanActivation(0);
    });
    return () => {
      unsubFrame();
      unsubReset();
    };
  }, []);

  // Halo intensity follows mean activation. Breathing baseline is small (~±0.45z),
  // so the multipliers are tuned to make idle visibly alive without blowing out
  // peak (real-frame) activations.
  const cold = meanActivation < 0;
  const mag = Math.min(1, Math.abs(meanActivation) / 1.5);
  const innerAlpha = cold ? 0.15 + mag * 0.55 : 0.2 + mag * 0.6;
  const outerAlpha = cold ? 0.08 + mag * 0.32 : 0.1 + mag * 0.4;
  const colorRGB = cold ? '56,124,255' : '255,140,40';
  const innerHalo = `rgba(${colorRGB},${innerAlpha.toFixed(3)})`;
  const outerHalo = `rgba(${colorRGB},${outerAlpha.toFixed(3)})`;

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
      {initError && (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center px-8 text-center">
          <div className="text-[10px] uppercase tracking-[0.28em] text-white/45">
            brain visualization unavailable
          </div>
          <div className="mt-2 text-xs text-white/55">
            WebGL2 not supported in this browser.
          </div>
          <div className="mt-1 text-[10px] text-white/30">
            Analysis still works — try Chrome, Edge, or a recent Firefox to see the brain.
          </div>
        </div>
      )}
    </div>
  );
}
