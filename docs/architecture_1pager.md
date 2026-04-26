# Cortex — architecture 1-pager

> **One sentence:** A neuroscience model on a GX10 in our backpack tells creators what an average viewer's brain does with their draft, predicts engagement, and detects originality drift — all before they post.

## The two questions a creator asks before they post

| Question | How we answer it |
|---|---|
| **Will this work?** | Pool TRIBE v2's per-second whole-brain BOLD prediction into a 21-dim ROI feature vector. Feed it to a Ridge regressor trained on a corpus of real Shorts paired with views/follower counts. Output: predicted engagement rate + percentile band ("top 25% for your size"). |
| **Am I repeating myself?** | Persist past clips as `(TRIBE-pooled, transcript-embedding)` only — no raw video. Cosine-rank a new draft against the creator's library in <50ms. Surface top-3 with a per-region (visual / auditory / language) breakdown chip. |

Both questions fall out of the **same TRIBE pooling** — one inference pass per draft.

## Stack at a glance

```
┌─────────────────────────────────────────┐    ┌────────────────────────────────────────────┐
│  Next.js 14 App Router                  │    │  ASUS GX10 (128GB unified memory)          │
│  ────────────────────────────           │    │  ────────────────────────────────          │
│  /         landing                      │    │  FastAPI + sse-starlette  :8080            │
│  /predict  upload + brain + predict     │    │                                            │
│  /library  past clips, length+timestamp │    │  TRIBE v2 (LLaMA-3.2-3B + V-JEPA2 +        │
│                                         │    │             Wav2Vec-BERT)        ~30 GB    │
│  Niivue (fsaverage5, 20484 verts)       │    │  Gemma 2B (text rewrites)        ~5 GB     │
│  EventSource for SSE brain frames       │    │  Whisper-base + nomic-embed      ~700 MB   │
│  Zustand for state                      │◄──►│  Ridge regressor + corpus.jsonl  KB        │
│                                         │    │  Per-creator library JSON        ~8 KB/clip │
└─────────────────────────────────────────┘    └────────────────────────────────────────────┘
                       ↕
              HTTP/JSON + SSE over Tailscale (WireGuard)
              Nothing leaves the box.
```

## Data flow per video draft

```
1. user drops mp4    →   POST /analyze/video                                 < 200 ms
2. /stream {job_id}  →   TRIBE: (T, 20484) z-scored BOLD                     ~25-40 s
                     →   pool to 21-dim ROI vector + ROI means + transcript
                     →   SSE: started, transcript, brain_frame×N, cold_zones, complete
3. user clicks       →   POST /predict-engagement {job_id, followers}        < 100 ms
   "Predict"             ↳ predicted rate + percentile vs. corpus.jsonl
4. SimilarityPanel   →   POST /similarity {job_id, creator_id}               < 100 ms
   auto-renders          ↳ top-3 brain-similar past clips + ROI breakdown
5. user clicks       →   POST /library/from-job {job_id, creator_id}         < 50 ms
   "Add to Library"      ↳ reuses cached features — no TRIBE re-run
```

Steps 3-5 reuse cached job features. Inference happens once.

## What we deliberately did not build

| Out | Why |
|---|---|
| Auto-editing video by cutting cold zones | Wrong product. The diagnostic is the deliverable. Creator decides what to do with the feedback. |
| ChromaDB / SQLite / vector DB | <10k creator clips fit in 80MB RAM. Brute-force numpy cosine ranks in <50ms. No vector DB needed. |
| Cloud inference fallback | Local or nothing. The whole pitch is "your draft never leaves the box." |
| iOS/Android app, auth, multi-tenant | 36 hours. Single demo creator (`DEMO_CREATOR_ID`); auth is a one-file change later. |
| Live IG/TikTok scraping during demo | Both rate-limit aggressively. Seed corpus is 50 hand-pulled YT Shorts via yt-dlp; scraper-agent is roadmap. |

## Honest framing

We do not claim TRIBE v2 predicts content *quality*. The training labels (views/followers) are the algorithm's mood, not human taste. We predict **algorithmic engagement**, which is what creators actually optimize for. The percentile band against a real public corpus is what makes the number trustworthy — judges see "8.4% — top 25% at your account size", not "8.4%".

## Why the GX10 matters

128GB unified memory means the entire creator's back-catalog (TRIBE features + transcripts) lives in RAM. A creator with 10,000 past clips fits in 80MB; the rest of the box runs TRIBE + Gemma + Whisper + nomic-embed simultaneously with ~85GB headroom. No laptop has this. No cloud GPU has this latency.

## Repository

`Dhwani090/LAHacks26` · `cortex/web/` (frontend) · `cortex/gx10/` (backend) · `docs/PRD.md` for the full spec · `docs/TASKS.md` for the work queue · `.claude/skills/` for domain knowledge (TRIBE, Niivue, engagement-prediction, originality-search).
