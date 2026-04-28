// Magic numbers — frontend single source.
// CLAUDE.md §4 mandates this file holds every tuning constant.
// Backend mirror: cortex/gx10/brain/config.py.
// Edit here, not inline in components.
// See docs/PRD.md §10 for activation colormap stops.

export const TUNING = {
  // BrainMonitor
  IDLE_AZIMUTH_STEP_DEG: 0.15,
  INTERPOLATION_FPS: 30,
  TRIBE_FRAME_MS: 1000,
  // Playback rate: <1 plays slower than real-time so the eye can follow which
  // regions light up. 0.6× ≈ each TRIBE second takes ~1.7s wall-clock.
  PLAYBACK_RATE: 0.6,
  // Temporal EMA: 0..1 weight for the new frame in the displayed activation.
  // Lower = smoother flowing waves, higher = snappier per-frame transitions.
  TEMPORAL_BLEND: 0.18,
  // Spatial smoothing: each iteration replaces a vertex with the mean of itself
  // and its mesh-edge neighbors. More iterations = larger / softer blobs.
  // 4 iters on the ICBM152 LH/RH mesh produces the "growing pool" look the
  // demo wants instead of speckled per-vertex thresholding.
  SPATIAL_SMOOTH_ITERS: 4,
  // Idle-mode pulse — needs to read as "alive" from across the venue.
  // 0.15Hz ≈ 6.7s breathing cycle, fast enough to feel like a heartbeat
  // without looking restless.
  IDLE_BREATHE_HZ: 0.15,
  IDLE_BREATHE_AMPLITUDE_Z: 0.6,

  // Activation colormap
  COLD_THRESHOLD_Z: -0.5,
  HOT_THRESHOLD_Z: 1.0,

  // Network
  ANALYSIS_TIMEOUT_MS: 60_000,
  HEALTH_POLL_MS: 5_000,

  // UI
  MODE_TRANSITION_MS: 240,
  COLD_HIGHLIGHT_OPACITY: 0.4,

  // Text mode
  MAX_TEXT_WORDS: 500,

  // Audio / video — covers YT Shorts max (3min), IG Reels (90s), most TikToks.
  // Mirrors gx10/brain/config.py:MAX_CLIP_DURATION_S.
  MAX_MEDIA_SECONDS: 180,
  MIN_MEDIA_SECONDS: 15,

  // Originality / creator-library (PRD §11.6)
  SIMILARITY_MIN_LIBRARY_SIZE: 5,
  SIMILARITY_TOP_K: 3,
} as const;
