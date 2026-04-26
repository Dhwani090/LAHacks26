---
name: engagement-prediction
description: Patterns for the engagement-prediction model — yt-dlp ingest, TRIBE feature pooling, ridge-regression baseline, percentile rank, and the OpenClaw/NemoClaw scraper-agent roadmap path. Load this skill when working on cortex/gx10/scripts/ingest_shorts.py, brain/pooling.py, brain/predictor.py, brain/corpus.py, the /predict-engagement endpoint, or the EngagementCard frontend component.
---

# Engagement Prediction Skill

## When to load this skill
Any task that:
- Calls `yt-dlp` (CLI or `yt_dlp` Python module) for video ingest
- Touches `cortex/gx10/brain/pooling.py`, `predictor.py`, or `corpus.py`
- Implements or modifies `POST /predict-engagement`
- Builds or fits the regression model in `scripts/fit_predictor.py`
- Builds the `EngagementCard.tsx` frontend component

## The pipeline at a glance

```
yt-dlp -j <url>            → metadata: views, likes, comments, channel_follower_count, duration
yt-dlp -f mp4 <url>        → mp4 file
↓
TribeModel.predict(...)    → (T, 20484) z-scored BOLD
↓
pool_tribe_output(...)     → 25-dim feature vector
↓
append to corpus.jsonl: {tribe_features, log(followers), duration, engagement_rate}
↓ (offline, batch)
Ridge.fit(X, log(engagement_rate))   → engagement_predictor.pkl
↓ (online, per /predict-engagement)
predictor.predict(features ++ log(followers) ++ duration_s ++ n_cold_zones)
  → predicted_rate, percentile_vs_corpus
```

## yt-dlp invocation patterns

**Metadata only:**
```bash
yt-dlp -j --skip-download "https://www.youtube.com/shorts/XXXXX"
```
Returns one JSON object per line. Fields we care about:
- `view_count` (int) — primary engagement signal
- `like_count` (int) — secondary
- `comment_count` (int) — secondary
- `channel_follower_count` (int) — required for engagement rate. **Skip rows where this is missing or zero.**
- `duration` (float) — input feature
- `uploader` / `channel_id` — for de-duplication (don't let one creator dominate the corpus)
- `webpage_url`, `id`, `title`, `description`, `tags`

**Video download:**
```bash
yt-dlp -f 'mp4' -o "%(id)s.mp4" "<url>"
```

**Gotchas:**
- YouTube Shorts URLs (`/shorts/<id>`) work directly; `yt-dlp` handles the redirect.
- For Instagram Reels and TikTok, add `--cookies-from-browser firefox` (or chrome). Both platforms increasingly require auth even for "public" content. **For the hackathon: stick to YouTube Shorts unless extra time.**
- Rate limits: YouTube tolerates ~50 sequential requests before throttling. Insert `time.sleep(1)` between calls.
- `yt-dlp` is updated weekly. Pin a recent version in `requirements.txt` (`yt-dlp>=2024.12.0`) but be ready to upgrade if endpoints break.

**Python wrapper sketch (use `subprocess`, not the `yt_dlp` Python API — fewer edge cases):**
```python
import json, subprocess
def fetch_metadata(url: str) -> dict:
    r = subprocess.run(["yt-dlp", "-j", "--skip-download", url],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp metadata failed: {r.stderr[:300]}")
    return json.loads(r.stdout)
```

## TRIBE feature pooling (`pooling.py`)

The 20484-vertex output is too high-dim for N≤500 samples. Pool to ~25 features:

```python
import numpy as np

# Per-region vertex indices come from cortexlab — see tribe-inference skill §"Output processing".
ROI_GROUPS = {
    "visual":   ["V1", "V2", "MT_complex", "LO", "FG"],
    "auditory": ["A1", "auditory_belt", "STS_dorsal", "STS_ventral"],
    "language": ["IFG", "STG", "MTG_anterior", "Broca", "Wernicke"],
}

def pool_tribe_output(preds: np.ndarray, roi_indices: dict) -> np.ndarray:
    """preds: (T, 20484). Returns 1D feature vector of length ~24."""
    feats = []
    for group, region_names in ROI_GROUPS.items():
        all_indices = np.concatenate([roi_indices[r] for r in region_names if r in roi_indices])
        curve = preds[:, all_indices].mean(axis=1)  # (T,)
        feats.extend([
            curve.mean(),
            curve.max(),
            curve.min(),
            curve.std(),
            float(np.polyfit(np.arange(len(curve)), curve, 1)[0]),  # slope
            float((curve < 0).mean()),                                # fraction below zero
        ])
    # Globals
    global_curve = preds.mean(axis=1)
    feats.extend([
        global_curve.max(),
        float((preds < -0.5).any(axis=1).sum()),  # rough cold-zone duration in seconds
        float(preds.var()),
    ])
    return np.array(feats, dtype=np.float32)
```

**Determinism:** keep `ROI_GROUPS` and the order of `feats.append` calls stable. The fitted predictor pickle is column-position-sensitive.

## The model (`predictor.py`)

```python
import joblib, numpy as np
from sklearn.linear_model import Ridge

class EngagementPredictor:
    """Swappable interface — see PRD §11.2 TODO for upgrade path."""
    def __init__(self, model=None):
        self._model = model  # any sklearn-compatible regressor

    @classmethod
    def load(cls, path: str) -> "EngagementPredictor":
        return cls(model=joblib.load(path))

    def save(self, path: str) -> None:
        joblib.dump(self._model, path)

    def fit(self, X: np.ndarray, y_log: np.ndarray) -> None:
        self._model.fit(X, y_log)

    def predict(self, features: np.ndarray, followers: int, duration_s: float,
                n_cold_zones: int) -> dict:
        x = np.concatenate([
            features, [np.log1p(followers), duration_s, n_cold_zones]
        ]).reshape(1, -1)
        log_rate = float(self._model.predict(x)[0])
        rate = float(np.exp(log_rate))
        return {"predicted_rate": rate, "log_rate": log_rate}
```

**Model upgrade path** (see PRD §11.2 TODO — do this only after the v0 baseline is wired end-to-end):
- `from sklearn.ensemble import GradientBoostingRegressor` — drop-in, no new deps.
- `from xgboost import XGBRegressor` — adds `xgboost` to requirements; lands well in pitches.
- `from sklearn.neural_network import MLPRegressor` — "small neural net," but unlikely to beat ridge with N≤200.

**Sanity-check the fit before pickling:**
- Compute held-out R². Print it. If R² is severely negative (<−0.5), the corpus is too small or the features are noise — investigate before shipping.
- Predict on 3 known training rows; the predicted rate should be in the ballpark of the actual rate (not orders of magnitude off).

## Percentile rank (`corpus.py`)

```python
class Corpus:
    def __init__(self, path: str):
        with open(path) as f:
            self.rows = [json.loads(l) for l in f if l.strip()]
        self.rates = sorted(r["engagement_rate"] for r in self.rows)

    def percentile(self, rate: float) -> int:
        if not self.rates:
            return 50
        below = sum(1 for r in self.rates if r < rate)
        return int(round(100 * below / len(self.rates)))

    def median_followers(self) -> int:
        f = sorted(r["followers"] for r in self.rows if r.get("followers"))
        return f[len(f)//2] if f else 10_000
```

The corpus is also the backstop for the "followers field" default in `EngagementCard` — when the user hasn't typed a number, use `corpus.median_followers()`.

## Honest framing notes (for the demo + Devpost)

- **The target is `views/followers`, not raw views.** Always say "engagement rate" or "expected reach percentage." Saying "predicted views" without normalization invites the question *"how can you predict that without knowing the algorithm?"* — to which there's no good answer.
- **Engagement is mostly algorithmic noise.** The literature on social-media virality predicts ~10-25% of variance from content features. Frame the model as *"finding the predictable signal"* not *"predicting virality."* Judges respect transparency.
- **The corpus is small.** Be explicit: *"trained on 50 hand-curated YT Shorts as a seed set; the offline scraper agent grows it nightly."*
- **The scraper agent is roadmap.** Don't claim it ran during the hackathon unless it actually did. The honest pitch: *"OpenClaw / NemoClaw on the GX10 — agent runs in the background, harvests URLs, re-trains overnight. Today: cron + yt-dlp. Tomorrow: agent."*
- **Don't claim we predict quality.** We predict what the YouTube/TikTok algorithm will reward. Those are correlated but distinct. A creator wants the latter; that's what we deliver.

## What NOT to do

- **Don't scrape Instagram Reels or TikTok with random GitHub scrapers.** Both platforms are hostile and most third-party scrapers are abandoned within months. Stick to `yt-dlp`.
- **Don't train on >500 videos in the hackathon.** TRIBE inference is the bottleneck (~30s per video). Even 50 videos = ~25 minutes of TRIBE time. Plan accordingly.
- **Don't bundle the `corpus.jsonl` into git.** Cache it on the GX10. Ship a 5-row example file as a schema reference.
- **Don't use a transformer model on raw frames.** TRIBE *is* the visual+audio+language encoder. Pooling its output and running a tiny regressor on top is the entire point.
- **Don't fine-tune TRIBE itself.** It's gated under CC-BY-NC and the model card explicitly says fine-tuning isn't supported. We learn a head on top of frozen features.

## Reference repos
- https://github.com/yt-dlp/yt-dlp (CLI + library)
- https://scikit-learn.org/stable/modules/linear_model.html#ridge-regression
- See also: `@.claude/skills/tribe-inference/SKILL.md` for ROI vertex indices and TRIBE call patterns.
