# Cortex — Devpost draft

> A neuroscience model tells creators what the average viewer's brain does with their draft, before they post. Two questions, one signal: *will this work?* and *am I repeating myself?*

## Inspiration

Most short-form creators ship and wait two weeks for analytics to know if a clip landed. By then it's irrelevant. The post is gone. The next idea has a deadline.

Meta FAIR released **TRIBE v2** in March 2026: a model that takes naturalistic video, audio, or text and predicts the average human's whole-brain BOLD response on a per-second basis. Trained on humans watching real content while their brains were being scanned. We saw it and asked one question: what if a creator could see this signal *before* they posted?

The whole project is built on the belief that the brain signal is the right substrate for two creator workflows that don't currently have good tools:

1. **Predict engagement**, not in views (which is mostly the algorithm's mood) but in views-per-follower — and tell the creator where their draft sits in a percentile distribution against real public content at their account size.
2. **Detect originality drift** — when the brain pattern of your new draft is 90% similar to one of your past clips, you've already made this video.

## What it does

**Three modes, one engine:**

- **Text** (≤500 words). Paste a draft. Get a per-sentence brain heatmap. Click any sentence that went cold; Gemma 2B suggests a rewrite that preserves the claim. Re-render in 5 seconds.
- **Audio** (15–180s). Drop a podcast clip. Watch a 2-track timeline (auditory cortex + language network) light up. See exactly where the listener tuned out.
- **Video** (15–180s, the spectacle). Drop a Short / Reel / TikTok draft. Visual + auditory + language tracks pulse alongside the playback. Click a red cold-zone band and the player jumps to that timestamp.

**On top of the brain analysis, two creator-facing pillars:**

- **Engagement prediction.** A scikit-learn model trained on TRIBE-pooled features from a corpus of real YouTube Shorts, paired with each clip's view count and the uploader's follower count. Predicts views-per-follower (engagement rate) on your draft, gives you a percentile band ("top 25% — this is hot for your audience size"), and lets you re-rank against any follower count instantly.
- **Originality search.** Your past clips persist as TRIBE feature vectors + Whisper transcripts + nomic-embed text embeddings — **no raw video kept on disk**. When you upload a new draft, we cosine-rank against your back catalog in <100ms and tell you which past clip your new one's brain pattern most resembles, with a per-region (visual/auditory/language) breakdown chip.

The whole thing runs on the **ASUS GX10 (128GB unified memory) sitting in our backpack**, talking to a Next.js + Niivue web app over Tailscale. Nothing leaves the box.

## How we built it

**Frontend** (`cortex/web/`): Next.js 14 App Router · TypeScript · Tailwind · `@niivue/niivue` for the cortical surface render · `framer-motion` · native `fetch` + `EventSource` over Tailscale. Three routes: `/` (landing), `/predict` (upload + brain + engagement + originality), `/library` (past clips with metadata).

**Backend** (`cortex/gx10/`): Python 3.11 · FastAPI + `sse-starlette` · TRIBE v2 (`tribev2` from `git+https://github.com/facebookresearch/tribev2.git`) · Gemma 2B for text rewrites · scikit-learn (Ridge regression baseline; the predictor class is intentionally swappable for GBR/XGBoost/MLP — see `predictor.py`) · Whisper-base for audio transcription · `nomic-embed-text-v1.5` for transcript embeddings · `yt-dlp` for the seed corpus.

**Storage**: filesystem JSON only. **No ChromaDB, no SQLite, no vector DB.** The corpus is a single `corpus.jsonl`. The creator library is per-creator JSON files holding the 21-dim TRIBE-pooled vector + 768-dim text embedding + transcript. With <10k clips, brute-force numpy cosine ranks in <50ms — no FAISS needed.

**Data flow** (per draft):

```
mp4  →  TRIBE v2  →  (T, 20484) z-scored BOLD predictions
                  ↓
            pool to 21-dim ROI feature vector  →  Ridge predictor  →  predicted engagement rate, percentile vs. corpus
                  ↓
            Whisper transcript  →  nomic-embed  →  cosine-rank against creator library  →  top 3 brain-twins
```

Everything except the live SSE frame stream is HTTP/JSON. The brain visualization is 1Hz from TRIBE, smoothstep-interpolated to 30fps client-side so the animation is buttery instead of stepping.

## What we're proud of

- **Two creator workflows on one model.** Engagement prediction and originality search both fall out of the same TRIBE pooling — no extra inference passes.
- **The library never stores raw video.** 21 floats + 768 floats + transcript text per clip. A creator with 10,000 past clips fits in 80MB; the box laughs.
- **Honest framing.** We don't claim TRIBE predicts quality. We predict *algorithmic engagement*, which is what creators actually optimize. The percentile band is anchored to a real public corpus, not a vibes number.
- **Demo robustness.** "Try a sample" button serves a cached hero clip in <2s. Status chip shows GX10 health every 5s — when the box drops, the chip flips and a cached fallback kicks in. Nobody sees a broken state.

## What we learned

- TRIBE v2's output is opinionated about input format. The first cycle was wrestling with NumPy < 2.1 ABI pinning and LLaMA gating before any inference happened.
- "Predict engagement" without a reference distribution is worse than no number. The percentile band against `corpus.jsonl` is what makes the prediction load-bearing in the demo — judges don't want "8.4%", they want "8.4% — top 25% for your size."
- A 1Hz model rendering at 30fps needs smoothstep easing or it visibly jolts. We linear-interped first; it looked like a slideshow. `t * t * (3 - 2 * t)` fixed it.
- Lazy-loading Whisper + nomic at first `/library/upload` instead of at server boot keeps `/health` instant. The user pays the cold-load tax once, hidden behind the upload progress UI.

## What's next

- **Tougher predictor.** The pluggable interface in `predictor.py` is one constructor call away from XGBoost or a small MLP. We tested Ridge first because we wanted the pipeline end-to-end before tuning the model.
- **Scraper agent.** OpenClaw / NemoClaw browser-agent loop running on the GX10 to harvest trending Shorts URLs autonomously and re-fit the predictor nightly. The cron-style entrypoint already exists; the agent is the future-tense story.
- **Multi-tenant library.** Currently single-creator demo build (`DEMO_CREATOR_ID = "demo"`). Adding auth + per-creator isolation is a one-file change on the frontend, no backend rewrite.
- **Cuts-on-cold-zones (rejected, intentionally).** We considered auto-editing low-engagement spans and removed it — it's the wrong product. The diagnostic *is* the deliverable; the creator decides what to do with the brain feedback.

## Built with

- Python 3.11, FastAPI, sse-starlette, Pydantic v2
- TRIBE v2 (Meta FAIR, March 2026), LLaMA-3.2-3B, V-JEPA2, Wav2Vec-BERT
- Gemma 2B (Google)
- scikit-learn, joblib (Ridge regression baseline; GBR/XGBoost ready)
- openai-whisper (base), sentence-transformers + nomic-embed-text-v1.5
- yt-dlp (seed corpus + future scraper-agent path)
- Next.js 14 App Router, TypeScript, Tailwind, @niivue/niivue, framer-motion, Zustand
- Tailscale (laptop ↔ GX10 over WireGuard)
- ASUS GX10 with 128GB unified memory

## Try it yourself

The demo lives on the GX10 at the LA Hacks venue. After the hackathon: the repo is at `Dhwani090/LAHacks26`, branches `engagement-prediction` and `pages-restructure` already merged. `cortex/gx10/` for the backend, `cortex/web/` for the frontend. The README in each has setup notes; you'll need an `HF_TOKEN` for TRIBE/Gemma/LLaMA gating.
