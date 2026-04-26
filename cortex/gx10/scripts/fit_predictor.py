#!/usr/bin/env python3
"""Fit the engagement predictor from corpus.jsonl.

PRD §11.2 + §11.7 + .claude/skills/engagement-prediction/SKILL.md §"The model".

Read corpus → drop `excluded:true` rows → build (X, y) where
X = [pooled_features ++ log(followers+1) ++ duration_s ++ n_cold_zones],
y = log(engagement_rate). Fit Ridge by default; --model can swap. 80/20 split,
deterministic seed. Print held-out R² and a sample-prediction table.

Importable as `fit_predictor(...)` so the NemoClaw curator (PRD §11.7) can
refit in-process and read back R² for the rollback decision.

Usage:
    python scripts/fit_predictor.py
    python scripts/fit_predictor.py --model gbr        # gradient boosted (no extra dep)
    python scripts/fit_predictor.py --corpus path.jsonl --out path.pkl

Output:
    cache/engagement_predictor.pkl
    spikes/predictor_metrics.md (held-out R², MAE, sample predictions)
"""
from __future__ import annotations
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow `from brain import ...` when run from cortex/gx10/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from brain import config  # noqa: E402
from brain.pooling import EXTRA_CONTEXT_COLUMNS, FEATURE_COLUMNS, POOLED_DIM  # noqa: E402
from brain.predictor import EngagementPredictor  # noqa: E402

logger = logging.getLogger("fit_predictor")


def _build_estimator(name: str) -> Any:
    if name == "ridge":
        from sklearn.linear_model import Ridge  # type: ignore
        return Ridge(alpha=1.0, random_state=0)
    if name == "gbr":
        from sklearn.ensemble import GradientBoostingRegressor  # type: ignore
        return GradientBoostingRegressor(random_state=0)
    if name == "mlp":
        from sklearn.neural_network import MLPRegressor  # type: ignore
        return MLPRegressor(hidden_layer_sizes=(64, 16), max_iter=500, random_state=0)
    raise ValueError(f"unknown model name: {name}")


def _row_to_xy(row: dict[str, Any]) -> tuple[np.ndarray, float] | None:
    # PRD §11.7: rows the curator rejected on R² regression are kept on disk for
    # the audit trail but skipped by the fitter. Same for any future hand-flagged bad rows.
    if row.get("excluded") is True:
        return None
    feats = row.get("tribe_features")
    rate = row.get("engagement_rate")
    followers = row.get("followers")
    duration = row.get("duration_s")
    n_cold = row.get("n_cold_zones", 0)
    if not isinstance(feats, list) or len(feats) != POOLED_DIM:
        return None
    if not isinstance(rate, (int, float)) or rate <= 0:
        return None
    if not isinstance(followers, (int, float)) or followers <= 0:
        return None
    if not isinstance(duration, (int, float)) or duration <= 0:
        return None
    x = np.asarray(
        list(feats) + [float(np.log1p(followers)), float(duration), float(n_cold)],
        dtype=np.float32,
    )
    return x, float(np.log(rate))


def fit_predictor(
    corpus_path: Path,
    out_path: Path,
    model: str = "ridge",
    seed: int = 0,
    test_frac: float = 0.2,
    metrics_path: Path | None = None,
) -> dict[str, Any]:
    """In-process fit. Returns `{n_rows, r2, mae, version, out_path}`.

    Used by `scripts/fit_predictor.py main()` and by `brain.curator` for the
    R-03 in-process refit + R²-rollback path. Raises ValueError on bad input
    so the caller (curator) can rollback cleanly without parsing log strings.
    """
    if not corpus_path.exists():
        raise ValueError(f"corpus not found: {corpus_path}")

    rows = [json.loads(line) for line in corpus_path.read_text().splitlines() if line.strip()]
    pairs = [pair for r in rows if (pair := _row_to_xy(r)) is not None]
    if len(pairs) < 5:
        raise ValueError(f"need at least 5 valid rows, got {len(pairs)}")

    X = np.stack([p[0] for p in pairs])
    y = np.asarray([p[1] for p in pairs], dtype=np.float32)
    logger.info("dataset: n=%d, X=%s, y range=[%.3f, %.3f]", len(pairs), X.shape, y.min(), y.max())

    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(pairs))
    n_test = max(1, int(round(len(pairs) * test_frac)))
    test_idx = perm[:n_test]
    train_idx = perm[n_test:]

    estimator = _build_estimator(model)
    estimator.fit(X[train_idx], y[train_idx])
    y_pred = estimator.predict(X[test_idx])
    residuals = y[test_idx] - y_pred
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y[test_idx] - y[test_idx].mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    mae = float(np.mean(np.abs(residuals)))

    version = f"v0-{model}-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    predictor = EngagementPredictor(model=estimator, version=version)
    predictor.r2 = r2 if np.isfinite(r2) else None
    predictor.save(out_path)
    logger.info("wrote %s (version=%s, r2=%.4f)", out_path, version, r2)

    if metrics_path is not None:
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        sample_lines = []
        for i in test_idx[: min(5, n_test)]:
            true_rate = float(np.exp(y[i]))
            pred_rate = float(np.exp(estimator.predict(X[i:i + 1])[0]))
            sample_lines.append(f"| {i} | {true_rate:.4f} | {pred_rate:.4f} | {pred_rate / true_rate:.2f}× |")
        metrics_path.write_text(
            "\n".join([
                f"# predictor_metrics.md",
                "",
                f"- version: `{version}`",
                f"- model: `{model}`",
                f"- corpus path: `{corpus_path}`",
                f"- N rows: {len(pairs)}",
                f"- test fraction: {test_frac} (n_test={n_test})",
                f"- held-out R²: **{r2:.4f}**",
                f"- held-out MAE (log-rate space): {mae:.4f}",
                "",
                "## sample held-out predictions (rate space)",
                "",
                "| idx | true | predicted | ratio |",
                "|---|---|---|---|",
                *sample_lines,
                "",
            ]) + "\n",
            encoding="utf-8",
        )
        logger.info("metrics written → %s", metrics_path)

    return {
        "n_rows": len(pairs),
        "r2": r2,
        "mae": mae,
        "version": version,
        "out_path": str(out_path),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--corpus", type=Path, default=config.CACHE_DIR / "corpus.jsonl")
    p.add_argument("--out", type=Path, default=config.CACHE_DIR / "engagement_predictor.pkl")
    p.add_argument("--metrics", type=Path, default=config.GX10_ROOT / "spikes" / "predictor_metrics.md")
    p.add_argument("--model", choices=["ridge", "gbr", "mlp"], default="ridge")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--test-frac", type=float, default=0.2)
    args = p.parse_args()

    try:
        out = fit_predictor(
            corpus_path=args.corpus,
            out_path=args.out,
            model=args.model,
            seed=args.seed,
            test_frac=args.test_frac,
            metrics_path=args.metrics,
        )
    except ValueError as exc:
        logger.error("%s", exc)
        return 1
    print(f"R² = {out['r2']:.4f}  MAE(log) = {out['mae']:.4f}  N={out['n_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
