---
name: originality-search
description: Per-creator library + brain-similarity ranking. Load when touching `library.py`, `transcribe.py`, `text_embed.py`, `/similarity`, `/library/*`, or any frontend `SimilarityPanel`/`LibraryUploader` work.
---

# Creator-library originality search (PRD §11.6)

The thesis: a creator's entire short-form back-catalog lives in RAM as TRIBE features + transcript embeddings. When they upload a new draft, we cosine-rank against the library in <100ms and tell them which past clip is most brain-similar.

Two pillars on top of the same TRIBE pipeline: engagement prediction asks *"will this work?"*, originality search asks *"are you repeating yourself?"*

## Library entry shape

```python
# cortex/gx10/brain/library.py
from dataclasses import dataclass

@dataclass
class LibraryEntry:
    video_id: str
    uploaded_at: str            # ISO 8601
    duration_s: float
    tribe_pooled: np.ndarray    # shape (21,), float32
    tribe_per_roi: np.ndarray   # shape (T, 3), per-second visual/auditory/language curves (fallback for R14)
    transcript: str
    text_embedding: np.ndarray  # shape (768,), L2-normed (nomic-embed-text-v1.5)
    thumbnail_url: str | None = None
```

Persisted as `cache/library/<creator_id>/<video_id>.json`. Numpy arrays serialize as nested lists.

## Stacked-matrix cosine ranking — no FAISS

```python
def rank_similar(
    draft_brain: np.ndarray,        # (21,)
    draft_text: np.ndarray,         # (768,)
    library: list[LibraryEntry],
    top_k: int = 3,
    alpha: float = 0.6,             # SIMILARITY_BRAIN_WEIGHT
) -> list[dict]:
    if len(library) < 5:
        return []  # cold-start gate

    # Stack once per request — sub-ms for <10k entries.
    B = np.stack([e.tribe_pooled / np.linalg.norm(e.tribe_pooled) for e in library])  # (N, 21)
    T = np.stack([e.text_embedding for e in library])                                 # (N, 768) already L2
    db = draft_brain / np.linalg.norm(draft_brain)
    dt = draft_text  # already L2

    brain_sim = B @ db                                  # (N,)
    text_sim = T @ dt                                   # (N,)
    score = alpha * brain_sim + (1 - alpha) * text_sim  # (N,)

    idx = np.argsort(-score)[:top_k]
    return [_build_match(library[i], score[i], brain_sim[i], text_sim[i]) for i in idx]
```

**Key invariants:**
- L2-norm the brain vec at rank time (the pooled output isn't necessarily unit-norm). The text embedding from nomic-embed already is.
- Don't rebuild the stacked matrix more than once per request. For multi-tenant later, cache `(B, T)` keyed by `(creator_id, library_size)`.
- Brute-force is correct here. <10k entries × 768 dims ≈ <50ms in numpy. FAISS is unnecessary complexity at hackathon scale.

## ROI breakdown (the demo moment)

```python
ROI_GROUPS = {  # already in pooling.py
    "visual": [...],     # vertices in V1+V2+V3+V4
    "auditory": [...],   # A1+belt+parabelt
    "language": [...],   # Broca+Wernicke
}

def per_roi_similarity(draft_per_roi: np.ndarray, lib_per_roi: np.ndarray) -> dict[str, float]:
    """draft_per_roi: (T_a, 3), lib_per_roi: (T_b, 3) — durations differ.
    Pool each ROI curve to a single number (mean) and cosine the 3-vec pair."""
    a_pooled = draft_per_roi.mean(axis=0)  # (3,)
    b_pooled = lib_per_roi.mean(axis=0)
    sims = a_pooled * b_pooled / (np.abs(a_pooled) * np.abs(b_pooled) + 1e-8)
    return {"visual": float(sims[0]), "auditory": float(sims[1]), "language": float(sims[2])}
```

`dominant_roi = max(roi_breakdown, key=roi_breakdown.get)` powers the demo line *"your auditory cortex pattern matches this clip."*

## Whisper + nomic-embed loading

Both are heavy enough that lazy-loading at first `/library/upload` (not at server boot) keeps `/health` fast. The progress UI on uploader hides the cold-load tax.

```python
# cortex/gx10/brain/transcribe.py
_WHISPER = None
def _model():
    global _WHISPER
    if _WHISPER is None:
        import whisper
        _WHISPER = whisper.load_model("base")
    return _WHISPER

def transcribe(audio_path: Path) -> str:
    return _model().transcribe(str(audio_path), fp16=False)["text"].strip()
```

```python
# cortex/gx10/brain/text_embed.py
_EMBED = None
def _model():
    global _EMBED
    if _EMBED is None:
        from sentence_transformers import SentenceTransformer
        _EMBED = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)
    return _EMBED

def embed_text(s: str) -> np.ndarray:
    v = _model().encode(s, normalize_embeddings=True)  # already L2-normed
    return np.asarray(v, dtype=np.float32)
```

For Whisper on a Mac dev box without GPU, `fp16=False` avoids a known crash. On the GX10 with proper torch+CUDA, drop the flag.

## Cold-start gate

`SIMILARITY_MIN_LIBRARY_SIZE = 5` (in `config.py`). Below that, `/similarity` returns:
```json
{"matches": [], "library_size": N, "creator_id": "...", "message": "upload at least 5 past clips"}
```

The frontend `SimilarityPanel.tsx` hides itself entirely. Don't render an empty state — render nothing.

## Job-id plumbing for /similarity

The endpoint needs `pooled_features` + `text_embedding` for the *draft* job. Cache them in `_JOBS[job_id]` at the same place engagement features are cached (after the SSE `complete` for `/stream`):

```python
# cortex/gx10/brain/main.py — after analysis completes
_JOBS[job_id]["pooled_features"] = pooled
_JOBS[job_id]["text_embedding"] = embed_text(transcript)
_JOBS[job_id]["per_roi_curve"] = per_roi  # (T, 3) for the fallback R14 path
```

`/similarity` reads from this dict — same lifecycle as `/predict-engagement`.

## Risks worth checking before pitching

- **R13 (always-similar matches):** if everything ranks 0.85-0.95, drop `SIMILARITY_BRAIN_WEIGHT` to 0.4 (text dominates) or vice versa. Expose as a debug slider before deciding.
- **R14 (21-dim too coarse):** if matches feel noisy, swap `tribe_pooled` for `tribe_per_roi.flatten()` (180-540 dims depending on duration). Match scores get more discriminative.
- Don't re-train or re-tune in the demo — set α once, stick with it.

## Verification quick-check

```bash
# After uploading 5+ library clips for creator_id="hero":
JOB=$(curl -s -X POST .../analyze/video -F file=@hero.mp4 | jq -r .job_id)
# wait for stream complete...
curl -s -X POST .../similarity -H 'content-type: application/json' \
  -d "{\"job_id\":\"$JOB\",\"creator_id\":\"hero\"}" | jq .
# Expect 3 matches; roi_breakdown values not all equal; score ∈ (0, 1].
```
