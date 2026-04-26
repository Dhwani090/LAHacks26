# TRIBE feature pooling — (T, 20484) z-scored BOLD → fixed ~25-dim vector.
# PRD §8.3 + skills/engagement-prediction/SKILL.md.
# Pure deterministic function; column order is load-bearing for the fitted predictor pickle.
# ROI indices come from cortexlab.data.rois.get_hcp_roi_indices() on the GX10;
# a deterministic stub partition is used in laptop dev where cortexlab isn't installed.
# See .claude/skills/engagement-prediction/SKILL.md.

from __future__ import annotations
import logging
from typing import Any

import numpy as np

from . import config

logger = logging.getLogger(__name__)


# ROI groupings per .claude/skills/tribe-inference/SKILL.md §"Output processing".
ROI_GROUPS: dict[str, list[str]] = {
    "visual":   ["V1", "V2", "MT_complex", "LO", "FG"],
    "auditory": ["A1", "auditory_belt", "STS_dorsal", "STS_ventral"],
    "language": ["IFG", "STG", "MTG_anterior", "Broca", "Wernicke"],
}

# Fixed feature column names. The fitted predictor pickle is column-position-sensitive,
# so reordering this list invalidates pre-trained models.
FEATURE_COLUMNS: list[str] = [
    *(f"{group}_{stat}"
      for group in ("visual", "auditory", "language")
      for stat in ("mean", "max", "min", "std", "slope", "frac_below_zero")),
    "global_max",
    "cold_seconds",
    "global_var",
]
# Plus 3 contextual scalars appended at predict-time but not part of TRIBE pooling:
EXTRA_CONTEXT_COLUMNS = ["log_followers", "duration_s", "n_cold_zones"]

POOLED_DIM = len(FEATURE_COLUMNS)  # 21 (6 stats × 3 ROI groups + 3 globals)


def _stub_roi_indices(seed: int = 0) -> dict[str, np.ndarray]:
    """Deterministic random partition of 20484 vertices into the named ROIs.

    Used only when cortexlab isn't installed (laptop dev). Real GX10 calls
    `_load_real_roi_indices()` at module load.
    """
    rng = np.random.default_rng(seed)
    perm = rng.permutation(config.TRIBE_VERTEX_COUNT)
    region_names = sorted({r for regions in ROI_GROUPS.values() for r in regions})
    chunks = np.array_split(perm, len(region_names))
    return {name: chunks[i].astype(np.int64) for i, name in enumerate(region_names)}


def _load_real_roi_indices() -> dict[str, np.ndarray] | None:
    """Try to load the real cortexlab ROI mapping. Returns None if unavailable."""
    try:
        from cortexlab.data.rois import get_hcp_roi_indices  # type: ignore
    except Exception as exc:
        logger.warning("cortexlab not available — falling back to stub ROI indices: %s", exc)
        return None
    try:
        raw = get_hcp_roi_indices()
        return {name: np.asarray(idx, dtype=np.int64) for name, idx in raw.items()}
    except Exception as exc:
        logger.error("get_hcp_roi_indices() failed: %s", exc)
        return None


_ROI_INDICES: dict[str, np.ndarray] | None = None


def get_roi_indices() -> dict[str, np.ndarray]:
    """Lazy-load ROI indices once; cache for the process."""
    global _ROI_INDICES
    if _ROI_INDICES is None:
        _ROI_INDICES = _load_real_roi_indices() or _stub_roi_indices()
    return _ROI_INDICES


def _group_indices(roi_indices: dict[str, np.ndarray], region_names: list[str]) -> np.ndarray:
    parts = [roi_indices[r] for r in region_names if r in roi_indices]
    if not parts:
        # All region names missing — fall back to whole-cortex so we don't return empty.
        return np.arange(config.TRIBE_VERTEX_COUNT, dtype=np.int64)
    return np.concatenate(parts)


def pool_tribe_output(preds: np.ndarray, roi_indices: dict[str, np.ndarray] | None = None) -> np.ndarray:
    """Pool a (T, 20484) z-scored BOLD prediction array to a fixed POOLED_DIM vector.

    Pure function. Output order matches FEATURE_COLUMNS. NaN/inf are clamped to 0.
    """
    if preds.ndim != 2:
        raise ValueError(f"expected 2D (T, V) array, got shape {preds.shape}")
    if preds.shape[1] != config.TRIBE_VERTEX_COUNT:
        raise ValueError(f"expected V={config.TRIBE_VERTEX_COUNT}, got {preds.shape[1]}")
    if preds.shape[0] < 2:
        # Slope is undefined on a single timestep; reject early so we don't ship NaNs.
        raise ValueError(f"need T >= 2 timesteps, got {preds.shape[0]}")

    indices = roi_indices if roi_indices is not None else get_roi_indices()

    feats: list[float] = []
    T = preds.shape[0]
    t_axis = np.arange(T, dtype=np.float32)

    for group in ("visual", "auditory", "language"):
        regions = ROI_GROUPS[group]
        idx = _group_indices(indices, regions)
        curve = preds[:, idx].mean(axis=1).astype(np.float32)  # (T,)
        slope = float(np.polyfit(t_axis, curve, 1)[0]) if T >= 2 else 0.0
        feats.extend([
            float(curve.mean()),
            float(curve.max()),
            float(curve.min()),
            float(curve.std()),
            slope,
            float((curve < 0).mean()),
        ])

    global_curve = preds.mean(axis=1)
    cold_seconds = float((preds < config.COLD_THRESHOLD_Z).any(axis=1).sum())
    feats.extend([
        float(global_curve.max()),
        cold_seconds,
        float(preds.var()),
    ])

    arr = np.asarray(feats, dtype=np.float32)
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)


def frames_to_array(brain_frames: list[dict[str, Any]]) -> np.ndarray:
    """Stack `[{t, activation}, ...]` (as TRIBE/stub returns) into (T, 20484) float32."""
    if not brain_frames:
        raise ValueError("empty brain_frames")
    arr = np.asarray([f["activation"] for f in brain_frames], dtype=np.float32)
    return arr


def roi_mean_vector(preds: np.ndarray, roi_indices: dict[str, np.ndarray] | None = None) -> np.ndarray:
    """Reduce (T, 20484) → (3,) — time-and-vertex mean per ROI group.

    Used by §11.6 originality search for the per-ROI breakdown chip
    ("auditory cortex match: 95%"). Distinct from `pool_tribe_output`,
    which returns 21 stats per ROI; this is the cleaner 3-number signal
    for the cosine-similarity tie-breaker.
    """
    if preds.ndim != 2 or preds.shape[1] != config.TRIBE_VERTEX_COUNT:
        raise ValueError(f"expected (T, {config.TRIBE_VERTEX_COUNT}), got {preds.shape}")
    indices = roi_indices if roi_indices is not None else get_roi_indices()
    out = np.zeros(3, dtype=np.float32)
    for i, group in enumerate(("visual", "auditory", "language")):
        idx = _group_indices(indices, ROI_GROUPS[group])
        out[i] = float(preds[:, idx].mean())
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
