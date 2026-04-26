# Pooling unit tests — pure-function shape, determinism, NaN-safety.
# PRD §8.3.

import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("CORTEX_STUB_TRIBE", "1")
os.environ.setdefault("CORTEX_STUB_GEMMA", "1")

from brain import config  # noqa: E402
from brain.pooling import (  # noqa: E402
    EXTRA_CONTEXT_COLUMNS,
    FEATURE_COLUMNS,
    POOLED_DIM,
    _stub_roi_indices,
    frames_to_array,
    pool_tribe_output,
)


def _fake_preds(T: int = 30, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(size=(T, config.TRIBE_VERTEX_COUNT)).astype(np.float32)


def test_pooled_shape_matches_columns():
    indices = _stub_roi_indices()
    out = pool_tribe_output(_fake_preds(), indices)
    assert out.shape == (POOLED_DIM,)
    assert len(FEATURE_COLUMNS) == POOLED_DIM
    assert len(EXTRA_CONTEXT_COLUMNS) == 3


def test_pooling_is_deterministic_given_same_indices():
    indices = _stub_roi_indices()
    a = pool_tribe_output(_fake_preds(seed=7), indices)
    b = pool_tribe_output(_fake_preds(seed=7), indices)
    np.testing.assert_array_equal(a, b)


def test_pooling_handles_nan_inf():
    preds = _fake_preds()
    preds[0, 0] = np.nan
    preds[1, 1] = np.inf
    out = pool_tribe_output(preds, _stub_roi_indices())
    assert np.isfinite(out).all()


def test_pooling_rejects_wrong_shapes():
    with pytest.raises(ValueError):
        pool_tribe_output(np.zeros((30, 100)), _stub_roi_indices())
    with pytest.raises(ValueError):
        pool_tribe_output(np.zeros((1, config.TRIBE_VERTEX_COUNT)), _stub_roi_indices())


def test_frames_to_array_stacks_correctly():
    frames = [
        {"t": 0.0, "activation": [0.1] * config.TRIBE_VERTEX_COUNT},
        {"t": 1.0, "activation": [0.2] * config.TRIBE_VERTEX_COUNT},
    ]
    arr = frames_to_array(frames)
    assert arr.shape == (2, config.TRIBE_VERTEX_COUNT)
    assert np.isclose(arr[0, 0], 0.1)
    assert np.isclose(arr[1, 0], 0.2)


def test_end_to_end_with_stub_tribe_output():
    """Verify pooled features can be derived from what TribeService.analyze_video returns."""
    from brain.tribe import tribe_service
    tribe_service.load()
    result = tribe_service.analyze_video(Path("/tmp/fake.mp4"))
    arr = frames_to_array(result["brain_frames"])
    pooled = pool_tribe_output(arr, _stub_roi_indices())
    assert pooled.shape == (POOLED_DIM,)
    assert np.isfinite(pooled).all()
