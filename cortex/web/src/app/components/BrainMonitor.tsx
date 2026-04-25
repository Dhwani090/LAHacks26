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
  const rafRef = useRef<number | null>(null);
  const idleRafRef = useRef<number | null>(null);
  const [meanActivation, setMeanActivation] = useState(0);

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

      const mesh = nv.meshes[0];
      if (mesh?.rgba255) {
        meshVertCountRef.current = Math.floor(mesh.rgba255.length / 4);
      } else if (mesh?.pts) {
        meshVertCountRef.current = Math.floor(mesh.pts.length / 3);
      }

      nv.setRenderAzimuthElevation(120, 15);
      nv.opts.dragMode = 0;

      const tick = () => {
        if (cancelled || !nvRef.current) return;
        nv.scene.renderAzimuth =
          (nv.scene.renderAzimuth + TUNING.IDLE_AZIMUTH_STEP_DEG) % 360;
        nv.drawScene();
        idleRafRef.current = requestAnimationFrame(tick);
      };
      idleRafRef.current = requestAnimationFrame(tick);
    })();

    return () => {
      cancelled = true;
      if (idleRafRef.current !== null) cancelAnimationFrame(idleRafRef.current);
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      idleRafRef.current = null;
      rafRef.current = null;
      nvRef.current = null;
    };
  }, []);

  useEffect(() => {
    const unsubFrame = frameBus.subscribe((frame) => {
      framesRef.current.push(frame);
      if (playStartMsRef.current === null) {
        playStartMsRef.current = performance.now();
        startPlayback();
      }
    });
    const unsubReset = frameBus.onReset(() => {
      framesRef.current = [];
      playStartMsRef.current = null;
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      setMeanActivation(0);
    });
    return () => {
      unsubFrame();
      unsubReset();
    };
  }, []);

  function startPlayback() {
    const tick = () => {
      const nv = nvRef.current;
      if (!nv) return;
      const frames = framesRef.current;
      const startMs = playStartMsRef.current;
      if (!frames.length || startMs === null) {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }

      const elapsed = performance.now() - startMs;
      const exact = elapsed / TUNING.TRIBE_FRAME_MS;
      const i0 = Math.min(Math.floor(exact), frames.length - 1);
      const i1 = Math.min(i0 + 1, frames.length - 1);
      const t = Math.min(1, Math.max(0, exact - i0));

      const a = frames[i0].activation;
      const b = frames[i1].activation;
      const targetLen = meshVertCountRef.current || a.length;
      const interp = new Float32Array(targetLen);
      const stride = a.length / targetLen;
      let sum = 0;
      for (let v = 0; v < targetLen; v++) {
        const src = Math.min(a.length - 1, Math.floor(v * stride));
        const value = a[src] * (1 - t) + b[src] * t;
        interp[v] = value;
        sum += value;
      }
      const mean = sum / targetLen;
      setMeanActivation(mean);

      try {
        const mesh = nv.meshes[0];
        if (mesh?.rgba255 && mesh.rgba255.length === targetLen * 4) {
          const colors = activationToVertexColors(interp);
          // Mutate the existing Uint8Array in place so niivue's GPU upload picks it up
          // on the next draw without us reaching into the (mistyped) setMeshProperty API.
          mesh.rgba255.set(colors);
          nv.updateGLVolume();
        }
      } catch (err) {
        // Per-vertex coloring is best-effort on the placeholder mesh; the halo
        // around the canvas still gives visible feedback. Fail silently.
        if (process.env.NODE_ENV === 'development') {
          console.warn('[BrainMonitor] vertex color skip', err);
        }
      }

      // Stop the playback loop after the last frame has been rendered for ~500ms.
      if (i0 >= frames.length - 1 && elapsed > frames.length * TUNING.TRIBE_FRAME_MS + 500) {
        rafRef.current = null;
        return;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    if (rafRef.current === null) {
      rafRef.current = requestAnimationFrame(tick);
    }
  }

  // Halo intensity follows mean activation: blue for cold (z<0), orange for hot.
  const halo =
    meanActivation === 0
      ? 'rgba(255,255,255,0)'
      : meanActivation < 0
        ? `rgba(56,124,255,${Math.min(0.6, Math.abs(meanActivation) * 0.4)})`
        : `rgba(255,140,40,${Math.min(0.7, meanActivation * 0.5)})`;

  return (
    <div
      className="relative h-full w-full"
      style={{ boxShadow: `inset 0 0 120px 20px ${halo}` }}
    >
      <canvas
        ref={canvasRef}
        className="h-full w-full"
        data-testid="brain-monitor-canvas"
      />
    </div>
  );
}
