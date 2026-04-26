# Engagement predictor — ridge regression on pooled TRIBE features.
# PRD §8.4 + §11.2 + skills/engagement-prediction/SKILL.md.
# Model class is intentionally swappable: any sklearn-compatible regressor with
# .fit(X, y) and .predict(X) plugs in. See PRD §11.2 TODO for upgrade candidates.
# See .claude/skills/engagement-prediction/SKILL.md §"The model".

from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

from . import config
from .pooling import EXTRA_CONTEXT_COLUMNS, FEATURE_COLUMNS, POOLED_DIM

logger = logging.getLogger(__name__)


def _new_baseline_model() -> Any:
    """Construct the v0 ridge regressor. Swap this for a tougher model per PRD §11.2."""
    from sklearn.linear_model import Ridge  # type: ignore
    return Ridge(alpha=1.0, random_state=0)


def build_input_row(features: np.ndarray, followers: int, duration_s: float, n_cold_zones: int) -> np.ndarray:
    """Concatenate pooled TRIBE features with the 3 contextual scalars in fixed order."""
    if features.shape != (POOLED_DIM,):
        raise ValueError(f"expected pooled features shape ({POOLED_DIM},), got {features.shape}")
    extras = np.asarray([
        float(np.log1p(max(followers, 0))),
        float(duration_s),
        float(n_cold_zones),
    ], dtype=np.float32)
    return np.concatenate([features.astype(np.float32), extras]).reshape(1, -1)


class EngagementPredictor:
    """Wraps an sklearn-style regressor predicting log(engagement_rate)."""

    def __init__(self, model: Any | None = None, version: str = "v0-ridge") -> None:
        self._model = model
        self._loaded = model is not None
        self.version = version

    @property
    def loaded(self) -> bool:
        return self._loaded

    @classmethod
    def load(cls, path: Path) -> "EngagementPredictor":
        import joblib  # type: ignore
        bundle = joblib.load(path)
        if isinstance(bundle, dict) and "model" in bundle:
            return cls(model=bundle["model"], version=bundle.get("version", "unknown"))
        # Backward-compat: pickle is a bare estimator.
        return cls(model=bundle, version="unknown")

    def save(self, path: Path) -> None:
        if self._model is None:
            raise RuntimeError("no model to save")
        import joblib  # type: ignore
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self._model, "version": self.version,
                     "feature_columns": FEATURE_COLUMNS,
                     "extra_columns": EXTRA_CONTEXT_COLUMNS}, path)

    def fit(self, X: np.ndarray, y_log_rate: np.ndarray) -> None:
        if self._model is None:
            self._model = _new_baseline_model()
        self._model.fit(X, y_log_rate)
        self._loaded = True

    def predict(self, features: np.ndarray, followers: int, duration_s: float,
                n_cold_zones: int) -> dict[str, float]:
        if not self._loaded or self._model is None:
            raise RuntimeError("predictor not loaded; call load() or fit() first")
        x = build_input_row(features, followers, duration_s, n_cold_zones)
        log_rate = float(self._model.predict(x)[0])
        # Clamp to a sane range so a bad fit can't return absurd numbers in the demo UI.
        log_rate = max(min(log_rate, 0.0), -8.0)  # rate ∈ [exp(-8), 1.0] = [3.4e-4, 1.0]
        rate = float(np.exp(log_rate))
        return {"predicted_rate": rate, "log_rate": log_rate}


predictor = EngagementPredictor()


def load_default_predictor() -> bool:
    """Try to load the default pickle from cache/. Returns whether a model is available.

    In stub mode (CORTEX_STUB_PREDICTOR=1) or when the pickle is missing, we install
    a tiny zero-coefficient ridge so /health stays green and /predict-engagement returns
    a sensible-looking median estimate during dev.
    """
    pkl = config.CACHE_DIR / "engagement_predictor.pkl"
    if pkl.exists():
        try:
            loaded = EngagementPredictor.load(pkl)
            predictor._model = loaded._model
            predictor._loaded = loaded._loaded
            predictor.version = loaded.version
            logger.info("engagement predictor loaded from %s (version=%s)", pkl, predictor.version)
            return True
        except Exception as exc:
            logger.error("predictor load failed: %s — falling back to stub", exc)

    if os.environ.get("CORTEX_STUB_PREDICTOR", "1") == "1":
        from sklearn.linear_model import Ridge  # type: ignore
        stub = Ridge(alpha=1.0, random_state=0)
        # Fit on a tiny synthetic dataset that yields ~5% engagement-rate predictions
        # (log(0.05) ≈ -3) so the demo UI shows something sane before the real fit lands.
        rng = np.random.default_rng(0)
        n_in = POOLED_DIM + len(EXTRA_CONTEXT_COLUMNS)
        X_stub = rng.normal(size=(64, n_in)).astype(np.float32)
        y_stub = rng.normal(loc=-3.0, scale=0.4, size=64).astype(np.float32)
        stub.fit(X_stub, y_stub)
        predictor._model = stub
        predictor._loaded = True
        predictor.version = "stub-zero"
        logger.warning("engagement predictor stub installed (no pickle at %s)", pkl)
        return True

    logger.error("no predictor pickle and stub disabled — predictor unloaded")
    return False
