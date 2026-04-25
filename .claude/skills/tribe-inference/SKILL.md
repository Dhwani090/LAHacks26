---
name: tribe-inference
description: Patterns for calling TRIBE v2 inference. Load this skill when working on any backend code that calls TribeModel, processes its outputs, or sets up the inference environment. TRIBE was released March 2026 — Claude's training data predates it.
---

# TRIBE v2 Inference Skill

## When to load this skill
Any task that:
- Imports from `tribev2` or `cortexlab.inference`
- Calls `TribeModel.from_pretrained()` or `model.predict()`
- Processes prediction arrays of shape `(n_timesteps, 20484)`
- Touches `gx10/brain/tribe.py` or `gx10/scripts/prerender_heroes.py`
- Debugs LLaMA gating, NumPy ABI, or HF download issues

## Critical environment gotchas (DataCamp tutorial)

These will eat hours if you hit them cold:

1. **Pin `numpy<2.1` BEFORE installing tribev2.** NumPy 2.x ABI breaks the build silently. Symptom: `ImportError` on `import tribev2` mentioning ndarray symbol mismatch.

2. **Set `HF_HUB_DOWNLOAD_TIMEOUT=300`.** Default timeout is too short for the 6GB LLaMA download on hackathon Wi-Fi. Symptom: `HfHubHTTPError: timeout`.

3. **Pre-download LLaMA before first `model.predict()`.** Don't let TRIBE trigger the download mid-inference.
   ```python
   from huggingface_hub import snapshot_download
   snapshot_download('meta-llama/Llama-3.2-3B')
   ```

4. **Always write → flush → fsync → close temp files** before passing paths to TRIBE. Race conditions otherwise.
   ```python
   with open(temp_path, 'w', encoding='utf-8') as f:
       f.write(content)
       f.flush()
       os.fsync(f.fileno())
   model.get_events_dataframe(text_path=temp_path)
   ```

5. **Encoding must be explicit.** `encoding='utf-8'` on every file open or you'll hit platform-dependent failures.

## Canonical inference call

```python
from cortexlab.inference.predictor import TribeModel

# Load once at server startup (NOT per request)
model = TribeModel.from_pretrained("facebook/tribev2", device="auto")

# Per request:
events_df = model.get_events_dataframe(video_path=str(video_path))
# OR audio_path=..., OR text_path=...

preds, segments = model.predict(events=events_df)
# preds shape: (n_timesteps, 20484)
# values: z-scored BOLD predictions
# offset: 5 seconds in the past (hemodynamic lag compensation)
# 1 Hz output
```

## Output processing

The 20,484 vertices map to the fsaverage5 cortical mesh. To aggregate into engagement curves per region, use ROI indices from cortexlab:

```python
from cortexlab.data.rois import get_hcp_roi_indices

roi_indices = get_hcp_roi_indices()
# Returns dict: region_name → list of vertex indices

def compute_engagement_curve(preds, region_name):
    """Average activation over time for a region."""
    indices = roi_indices[region_name]
    return preds[:, indices].mean(axis=1)  # shape: (n_timesteps,)
```

For Cortex's three engagement tracks:
- **visual:** combine `V1`, `V2`, `MT_complex`, `LO`, `FG` regions
- **auditory:** combine `A1`, `auditory_belt`, `STS_dorsal`, `STS_ventral`
- **language:** combine `IFG`, `STG`, `MTG_anterior`, `Broca`, `Wernicke`

## Cold zone detection

A "cold zone" is a contiguous time range where engagement drops below threshold. Definition:

```python
COLD_THRESHOLD_Z = -0.5  # below this z-score = cold

def find_cold_zones(curve, min_duration_s=2.0, sample_rate_hz=1.0):
    """Returns list of (start_t, end_t, depth) tuples."""
    below = curve < COLD_THRESHOLD_Z
    # ... runs-of-true logic, filter by min_duration
```

Don't get clever — coarse zones are better for the demo than precise ones.

## Modality-specific inference paths

TRIBE supports running with subsets of modalities. This is critical for latency:

| Mode | Encoders used | Approx latency for 30s input |
|---|---|---|
| Text only | LLaMA only | 5-10s |
| Audio only | Wav2Vec + LLaMA (auto-transcribe) | 15s |
| Video full | V-JEPA + Wav2Vec + LLaMA | 25-40s |

To skip the video encoder for audio mode, pass only `audio_path` (no `video_path`). TRIBE handles modality selection automatically based on what's in the events dataframe.

## What TRIBE CANNOT do (don't accidentally promise these)

- **Personalize to an individual user** — predictions are population-average only
- **Predict sub-second phenomena** — 1 Hz output, can't see flicker, can't see micro-expressions
- **Resolve retinotopic / low-level visual areas accurately** — V-JEPA features are spatially averaged
- **Predict emotion / amygdala / subcortical regions** — cortical surface only
- **Operate on inputs <15s** — minimum useful input length per the paper
- **Provide uncertainty estimates** — no native confidence intervals

If a task description asks for any of the above, push back to the user before coding.

## License (relevant for Devpost copy)

- TRIBE weights: **CC BY-NC 4.0** (non-commercial only — fine for hackathon)
- TRIBE code: Apache-2.0
- LLaMA 3.2-3B: gated, requires Meta license acceptance
- cortexlab-toolkit: CC BY-NC 4.0

For the Devpost: state the licenses honestly. Judges respect transparency more than hand-waving.

## Reference repos
- https://github.com/facebookresearch/tribev2 (official, see `tribe_demo.ipynb`)
- https://github.com/siddhant-rajhans/cortexlab (toolkit we fork)
- https://www.datacamp.com/tutorial/tribe-v2-tutorial (gotchas documented)
