# PRD.md — Cortex

> **The product:** a pre-flight check for short-form content. Drop in a draft video and Cortex (a) renders what the average viewer's brain did with it via a foundation neuroscience model on the GX10, and (b) predicts the engagement rate it will get on YouTube Shorts / TikTok / Instagram Reels via a model trained on real public videos paired with their TRIBE brain features. Three input modes — text, audio, short-form video — share one engine and one brain visualization.
>
> **The pitch in one breath:** *"Every creator ships work guessing whether it'll land. Cortex tells you — by simulating the brain response and predicting engagement on a model trained from videos that already went viral."*
>
> **Demo day:** LA Hacks 2026, Sunday morning, UCLA Pauley Pavilion. **36-hour build, 4-person team.**
>
> **Track:** Flicker to Flow (Productivity).
> **Sponsor stack:** ASUS Ascent GX10 + Cloudinary + MLH Best Use of Gemma + Best UI/UX. Stretch: Cognition.

---

## §0 — Success criteria (measurable wins)

The project succeeds if and only if all of these are true on Sunday morning:

1. **Demo runs end-to-end in <3 minutes** with all three modes (text, audio, video) demonstrated
2. **Judge can drop their own content** in any of the three modes and see a brain visualization within 60 seconds (or fall back gracefully to a cached hero clip)
3. **Engagement-prediction surface returns a numeric estimate** (predicted engagement rate + percentile vs. the seed corpus) for any uploaded video in <5s after TRIBE finishes
4. **Devpost submission is complete** with video, GitHub link, and all four sponsor/side-prize tracks tagged: Flicker to Flow, ASUS, Cloudinary, MLH Best Use of Gemma, Best UI/UX
5. **The brain visualization is visibly polished** — judges from 30 feet away should be drawn to the booth by the rotating glowing brain

If any of these aren't met by hour 30, focus the remaining time on the gap.

---

## §1 — Vision

Every writer, editor, marketer, podcaster, founder, and short-form creator ships content guessing whether it landed. They wait two weeks for analytics. Cortex closes the loop *before* upload. Drop in a script, an audio take, or a 30-second video, and three things happen:

1. **TRIBE v2** (Meta FAIR neuroscience model, released March 2026) predicts the average viewer's second-by-second neural engagement and renders it as a glowing cortical surface pulsing alongside the content.
2. The brain output is pooled into a feature vector that we feed to an **engagement-prediction model** trained on public YouTube Shorts paired with their real-world view/like/comment counts and the uploader's follower count. The user sees: *"predicted engagement rate: 8.4% (75th percentile of your account's recent videos)."*
3. For text mode, a small **Gemma 2B** model reads cold zones and proposes sentence rewrites the user can apply.

The model lives on the box: training data, training run, and inference all on the GX10. An offline scraper (described in §11.4 — `yt-dlp` for the demo build, NemoClaw active-learning agent in §11.7) pulls trending Shorts in the background and re-fits the model on each fresh batch.

Why this only works on this hardware: TRIBE v2 needs ~30GB VRAM with all encoders loaded. The GX10's 128GB unified memory holds TRIBE + Gemma + the predictor + a small training corpus concurrently, with sub-second response paths for text and ~25s for video inference. A laptop cannot hold TRIBE. A cloud API would round-trip the user's draft content — defeating the privacy story creators care about for unreleased work.

Why this only works now: TRIBE v2 was open-sourced one month ago. Most teams at LA Hacks 2026 will not have heard of it. Originality is asymmetric.

---

## §2 — Hard non-goals

- iOS or Android app — desktop web only
- User accounts, login, auth, OAuth, social sign-in
- Multi-day project history or shareable links
- Long-form content (>180 seconds video, >180 seconds audio, >500 words text). 180s is the platform-aware ceiling: YouTube Shorts now allows up to 3min, IG Reels max 90s, most TikToks <120s. Past that, the TRIBE pooling assumptions (per-clip ROI averaging) stop matching how creators think about short-form pacing.
- Auto-editing of video by cutting low-engagement spans (the cuts-on-cold-zones loop is removed — the diagnostic + the engagement number is the product)
- Auto-regeneration of new content (no B-roll generation, no voice synthesis, no music swap, no script rewriting beyond inline text-mode suggestions)
- Real-time live camera or microphone input
- Cloud inference fallback if the GX10 is down — local or nothing
- Multi-user collaboration, comments, sharing
- ChromaDB, vector stores, anything beyond filesystem JSON cache
- Phone-side ZETIC integration — explicitly skipped, do not bolt on
- Live scraping of Instagram Reels or TikTok during the demo — both platforms aggressively block scrapers and rate-limit, so the build path is **YouTube Shorts via `yt-dlp`** for the seed corpus; IG/TikTok are demoed as "pipeline-ready, runs on the box" but not relied on live
- Training the engagement model on >1k videos during the hackathon — seed set is 50–200 hand-pulled YT Shorts, retraining on bigger corpora is roadmap (the offline scraper agent is the future, not the demo)
- Anything discovered after hour 18 (scope freeze gate)

---

## §3 — Architecture overview

Two-tier, fully local during the demo, talking over Tailscale.

### Frontend (laptop, dev + demo)
- **Next.js 14** (App Router), TypeScript, **Tailwind CSS**
- **`@niivue/niivue` + `niivue-react`** for the brain monitor (BSD-2 license)
- **`framer-motion`** for tab/panel transitions
- **`@cloudinary/react`** for video upload widget (Cloudinary sponsor stack)
- Native `fetch` + `EventSource` (SSE) for backend comms

### Backend (GX10, Ubuntu, SSH-only via Tailscale)
- **Python 3.11**
- **FastAPI + uvicorn + `sse-starlette`**
- **`tribev2`** package from `git+https://github.com/facebookresearch/tribev2.git`
- **`cortexlab-toolkit`** as scaffolding source — fork their `inference/` and `analysis/` modules
- **`transformers` + Gemma 2B** for text-mode rewrite suggestions
- **`scikit-learn`** for the engagement-prediction model (ridge regression baseline; see §11.2 for the upgrade path)
- **`yt-dlp`** for ingesting YouTube Shorts (and, where it works, IG Reels / TikTok) into the training corpus
- **`openai-whisper` (base)** for audio→transcript on creator-library uploads (§11.6) — runs on the box, no API call
- **`sentence-transformers` (`nomic-embed-text-v1.5`)** for transcript embeddings used in originality search (§11.6)
- **`numpy`** stacked-matrix cosine for similarity ranking — no FAISS, no vector DB. <10k clips fits in <100MB and ranks in <50ms.
- In-memory cache + filesystem JSON cache + a single `corpus.jsonl` of `{video_id, tribe_features, engagement_rate, followers, ...}` rows + per-creator `cache/library/<creator_id>/*.json` for the originality library. **NO Chroma, NO SQLite.**
- Pydantic v2 for DTOs

### Transport
- HTTP/JSON for request/response
- SSE for streaming brain frames during analysis (1 Hz from TRIBE → smoothed to 30 fps client-side)
- All over Tailscale between laptop and GX10
- No WebSockets, no gRPC

### What's running where on the GX10
- Port 8080: FastAPI server (Cortex brain)
- TRIBE v2 + LLaMA-3.2-3B + V-JEPA2 + Wav2Vec-BERT loaded at startup (~30GB resident)
- Gemma 2B loaded at startup (~5GB resident)
- `engagement_predictor.pkl` (a scikit-learn ridge regressor over pooled TRIBE features) — kilobytes, loaded into RAM
- `corpus.jsonl` of pre-computed `{tribe_features, engagement_rate, followers}` rows — used both for training and as the percentile-rank reference at inference time (~10MB for 200 videos)
- Whisper-base (~150MB) + `nomic-embed-text-v1.5` (~550MB) loaded at startup for the originality library (§11.6)
- Per-creator library `cache/library/<creator_id>/*.json` — TRIBE features + transcript embedding + thumbnail per past clip. Loaded on demand into a `creator_id → list[LibraryEntry]` in-memory dict. ~8KB/clip; 10k clips = 80MB.
- Optional offline batch ingest: `yt-dlp` pulls a trending-Shorts batch → TRIBE runs over each → corpus appends → predictor refits. This is a separate `scripts/refit_predictor.py` invocation, not a service. **The agentic version is spec'd in §11.7 (active-learning corpus curator) — a single NemoClaw agent that runs in the uvicorn lifespan, picks what to scrape next via `yt-dlp ytsearch20:<query>` (no manual URL seed list), targets gaps in the current ridge predictor, and yields to live `/analyze/*` requests via a priority gate. The same agent rotates a "trending" iteration every 6 cycles to fill the pool that powers §11.8 (inspiration feed). NemoClaw chosen over OpenClaw to align with the NVIDIA NeMo stack on the GX10's Blackwell silicon.**
- Date-partitioned trending pool: `cache/trending/<yyyy-mm-dd>/*.json` — same TRIBE-pooled + transcript-embedding shape as a library entry. Refreshed every ~6h by the curator, 7-day TTL. Powers the inspiration feed (§11.8).
- Total resident: ~36-42GB of 128GB (TRIBE + Gemma + Whisper + nomic + corpus + creator libraries). The remaining ~85GB is room for very large creator libraries — a creator with 5,000 past clips fits with multiple GB to spare.

---

## §4 — Pre-hackathon prep (MUST happen by Wed April 23 EOD)

These eight tasks gate the entire project. If they aren't done by Wednesday, **abandon Cortex** and pivot to 3D Movement Coach. This is not optional.

| ID | Task | Owner | Hours | Verification |
|---|---|---|---|---|
| PH-A | Accept LLaMA 3.2 license at llama.meta.com → request HF access at `meta-llama/Llama-3.2-3B`. **Do this Monday.** | Anyone | 0.5 | HF dashboard shows "approved" |
| PH-B | SSH to GX10. Conda env `cortex` (Python 3.11). `pip install "numpy<2.1"`. `huggingface-cli login`. Install `tribev2` + `cortexlab-toolkit`. | Strongest engineer | 4-6 | `python -c "from cortexlab.inference.predictor import TribeModel; m = TribeModel.from_pretrained('facebook/tribev2', device='auto')"` succeeds |
| PH-C | Run TRIBE on a 30s test video end-to-end. Verify shape `(n_timesteps, 20484)`. Log latency. | Same | 1 | Output array of correct shape returned, latency noted in `spikes/tribe_latency.md` |
| PH-D | Local laptop: scaffold Next.js + Tailwind + `niivue-react`. Render the demo `BrainMesh_ICBM152.lh.mz3` mesh in browser. | Frontend lead | 2-3 | `npm run dev` shows rotating brain on `localhost:3000` |
| PH-E | Pre-render TRIBE outputs for 5 video hero clips. Cache as JSON on GX10. | PH-B owner | 1 | 5 JSON files at `gx10/cache/hero_video/*.json`, each loadable, each contains `brain_frames` of correct shape |
| PH-F | Pre-render TRIBE outputs for 5 audio clips. Cache as JSON. | Same | 0.5 | 5 JSON files at `gx10/cache/hero_audio/*.json` |
| PH-G | Pre-render text-mode outputs for 5 example paragraphs. Cache as JSON. | Same | 0.5 | 5 JSON files at `gx10/cache/hero_text/*.json` |
| PH-I | Build a 50-video YT Shorts seed corpus: `yt-dlp` pull → TRIBE over each → write `{video_id, pooled_features, views, likes, comments, followers, duration_s, engagement_rate}` rows to `gx10/cache/corpus.jsonl`. Hand-pick across 5 niches (cooking / explainer / pitch / comedy / fitness) so the predictor isn't single-domain. | PH-B owner | 3-4 | `wc -l gx10/cache/corpus.jsonl` ≥ 50; `python scripts/inspect_corpus.py` prints sane min/median/max engagement rates |
| PH-J | Fit the v0 engagement predictor on the seed corpus. Ridge regression on pooled features + log(followers) + duration. Serialize to `gx10/cache/engagement_predictor.pkl`. Print held-out R² (expect 0.05–0.25 — this is fine, most engagement is algorithmic noise). | PH-B owner | 1 | `python scripts/fit_predictor.py` writes the .pkl, prints `R² = <num>`, and a sanity prediction on a held-out video matches its actual rate within 0.5 std |

Total pre-hack budget: **~14-15 hours**. If PH-B fails by **Wed April 23 EOD**, pivot to 3D Movement Coach.

---

## §5 — Hardware + accounts

### Hardware
- ASUS Ascent GX10 (128GB unified memory, Blackwell, SSH-only via Tailscale)
- 2 laptops — one for dev/demo, one as backup
- 2 external monitors — left for Cortex UI, right for the brain
- 1 tablet for handing to judges
- JBL Bluetooth speaker (optional, for ElevenLabs stretch)

### Accounts and keys
| Key | Where it lives | Required for |
|---|---|---|
| HuggingFace token | `~/.bashrc` on GX10 | LLaMA 3.2-3B + TRIBE weights |
| Meta LLaMA license | Accepted at llama.meta.com | Gate clearance |
| Tailscale account | Both laptop + GX10 | Network transport |
| Cloudinary API key | `.env.local` on Next.js | Video upload widget |

**Not needed:** OpenAI, Anthropic, NVIDIA NGC, ZETIC Melange, GitHub PAT, ElevenLabs (unless P3-07 stretch).

---

## §6 — Three modes specification

### 6.1 Text mode (the fast loop)

**Input:** paste of up to 500 words.
**TRIBE pathway:** language only (LLaMA-3.2-3B encoder → fusion → cortical projection).
**Inference latency:** 5-10s.
**Output:** heatmap underline on text (cold → blue, hot → orange), brain pulse, suggestion panel.
**Edit loop:** click cold sentence → Gemma suggestion → apply → re-render in 5-10s.
**Verification:** paste hero text → see heatmap in <12s. Click cold sentence → suggestion appears. Apply → re-render shows warmed sentence.

### 6.2 Audio mode (the surprise)

**Input:** 15-180s audio clip (mp3, wav, m4a).
**TRIBE pathway:** audio + language (Wav2Vec-BERT + LLaMA, no V-JEPA).
**Inference latency:** ~15s.
**Output:** waveform + 2-track timeline (auditory green, language orange), brain pulses (no visual cortex).
**Verification:** drop hero audio → 2-track timeline visible within 18s. Brain shows quieter activation than video mode (auditory + language only).

### 6.3 Video mode (the spectacle + engagement prediction)

**Input:** 15-180s video clip (mp4, mov), plus an optional `followers` integer the user types in (defaults to median of corpus).
**TRIBE pathway:** full trimodal.
**Inference latency:** ~25-40s for TRIBE; the predictor runs in <50ms once features land.
**Output:**
- Video player + 3-track timeline (visual blue, auditory green, language orange), brain syncs to playback. Cold zones highlighted in red on the timeline.
- Engagement card: predicted rate (e.g. *"8.4% expected"* — views/followers, log-space prediction exponentiated for display) + percentile vs. the seed corpus + a one-line interpretation (*"top 25% — this is hot for your audience size"*).
- Originality panel (§11.6): top 3 most-similar past clips from the creator's library, each with a similarity score + per-ROI breakdown chip (*"auditory cortex match: 95%"*). Hidden if library < 5 clips.

**Verification:** drop hero clip → 3-track timeline visible within 45s. Play video → brain pulses in sync. Click red cold zone → player jumps to that timestamp. Engagement card renders within 1s after TRIBE complete. Originality panel renders within 100ms after engagement card lands (in-memory cosine).

---

## §7 — Frontend modules (Next.js)

```
app/
├── layout.tsx              # Three-tab shell
├── page.tsx                # Main route
├── components/
│   ├── BrainMonitor.tsx    # Niivue wrapper — see §10 + skills/niivue-rendering
│   ├── ModeTabs.tsx        # Text/Audio/Video toggle
│   ├── TextSurface.tsx     # Paste + heatmap + suggestions
│   ├── AudioSurface.tsx    # Audio uploader + waveform + 2-track timeline
│   ├── VideoSurface.tsx    # Video uploader + player + 3-track timeline + EngagementCard
│   ├── EngagementTimeline.tsx  # Reusable N-track timeline
│   ├── EngagementCard.tsx  # Predicted-engagement number + percentile + interpretation
│   ├── SimilarityPanel.tsx # §11.6 — top-3 past clips with ROI breakdown chips
│   ├── LibraryUploader.tsx # Bulk uploader for creator's past clips → /library/upload
│   ├── HeatmapText.tsx     # Per-word color overlay
│   ├── SuggestionPanel.tsx # Text-mode Gemma rewrite suggestions, click-to-apply
│   ├── StatusChip.tsx      # GX10 connection status
│   └── DebugOverlay.tsx    # Hideable debug info
├── lib/
│   ├── brainClient.ts      # fetch + EventSource wrapper
│   ├── cache.ts            # Local cache fallback
│   ├── types.ts            # TS DTOs matching Pydantic
│   ├── colormap.ts         # Activation → color
│   └── tuning.ts           # All magic numbers
└── state/
    └── AppState.ts         # Zustand store
```

### 7.1 BrainMonitor verification
- Hero clip pulses through visible activation states during analysis
- Idle state shows slow auto-rotate with breathing pulse
- Frame interpolation looks smooth (no visible 1Hz steps)
- See `@.claude/skills/niivue-rendering/SKILL.md` for implementation patterns

### 7.2 HeatmapText verification
- Hero text renders with visible color variation across sentences
- Cold sentences clearly distinguishable (faint blue)
- Click on cold sentence opens SuggestionPanel
- Re-render after edit fades old colors to new colors over 600ms

### 7.3 EngagementTimeline verification
- 3 tracks (video) or 2 tracks (audio) render below media element
- Cold zones visibly highlighted in red
- Vertical scrubber syncs to media playback
- Click on cold zone seeks the player to that timestamp

### 7.4 EngagementCard verification
- Renders within 1s of TRIBE `complete` event in video mode
- Shows predicted engagement rate (one decimal, %), percentile band ("top 25%" / "median" / "below average"), and a one-line plain-English interpretation
- Shows a "trained on N videos · last updated X" caption (transparent about corpus size)
- Followers field defaults to corpus-median; user can edit and the card re-renders client-side without re-running TRIBE

### 7.5 SimilarityPanel verification
- Hidden when library has <5 entries (cold-start gate)
- After EngagementCard lands, renders top 3 thumbnails with overall score + ROI breakdown chip in <100ms
- Click on a card opens a side drawer with the matched clip's metadata (uploaded date, duration, transcript snippet)
- Sanity check: same clip uploaded as both library + draft → top match is itself with score ~1.0

### 7.6 LibraryUploader verification
- Drag-drop multiple mp4s → POST `/library/upload` for each → progress bar per file
- Each upload triggers TRIBE + Whisper + transcript-embed pipeline; status reported via SSE
- After all uploads complete, library size badge updates and SimilarityPanel becomes available on next analysis

---

## §8 — Backend modules (FastAPI on GX10)

```
gx10/
├── brain/
│   ├── main.py              # FastAPI app, all endpoints
│   ├── config.py            # All tuning constants
│   ├── models.py            # Pydantic DTOs
│   ├── tribe.py             # TRIBE inference wrapper
│   ├── gemma.py             # Gemma 2B text-rewrite service
│   ├── predictor.py         # Engagement-prediction model (ridge regression on pooled TRIBE features)
│   ├── pooling.py           # TRIBE (T,20484) → ~25-dim feature vector via ROI grouping + stats
│   ├── corpus.py            # Reads/writes cache/corpus.jsonl; computes percentile ranks
│   ├── library.py           # §11.6 — per-creator library load/save + cosine ranking
│   ├── transcribe.py        # §11.6 — Whisper-base wrapper for audio→transcript
│   ├── text_embed.py        # §11.6 — nomic-embed-text wrapper, 768-dim L2-normed
│   ├── cache.py             # Filesystem JSON cache + fallback
│   ├── streaming.py         # SSE helpers
│   └── prompts.py           # All Gemma prompts
├── scripts/
│   ├── 00_tailscale_up.sh
│   ├── 01_start_brain.sh
│   ├── 99_healthcheck.sh
│   ├── prerender_heroes.py  # Pre-hack PH-E/F/G
│   ├── ingest_shorts.py     # yt-dlp pull → TRIBE → corpus.jsonl append (PH-I)
│   ├── fit_predictor.py     # Read corpus.jsonl → fit ridge → write engagement_predictor.pkl (PH-J)
│   └── refit_predictor.py   # Cron entrypoint: ingest a fresh batch → re-fit. Roadmap: replaced by NemoClaw curator (§11.7).
├── cache/
├── tests/
│   └── test_smoke.py
└── requirements.txt
```

### 8.1 `tribe.py` verification
- `analyze_text("hero text")` returns valid `TextAnalysisResult` in <12s (cache hit: <500ms)
- `analyze_audio(hero_path)` returns 2-curve result in <18s
- `analyze_video(hero_path)` returns 3-curve result in <45s
- See `@.claude/skills/tribe-inference/SKILL.md` for `TribeModel` patterns

### 8.2 `gemma.py` verification
- `suggest_edits(mode="text", cold_zones, transcript)` returns ≥1 valid `EditSuggestion` (rewrite of the cold sentence) in <3s

### 8.3 `pooling.py` verification
- `pool_tribe_output(preds: np.ndarray[T, 20484]) -> np.ndarray[~25]` returns a fixed-shape feature vector regardless of input duration
- For each ROI group (visual / auditory / language) computes: `mean, max, min, std, slope, fraction_below_zero` over the time-averaged ROI curve
- Plus global: `n_cold_zones, total_cold_duration, peak_global_activation`
- Pure function, deterministic given input

### 8.4 `predictor.py` verification
- `EngagementPredictor.load()` reads `cache/engagement_predictor.pkl` at server startup; `/health` reports `predictor_loaded: true`
- `predict(features, followers, duration_s) -> {predicted_rate: float, percentile: int}` returns in <50ms
- Percentile computed against `corpus.jsonl` rates; falls back to "median" if corpus is empty
- Model class is intentionally swappable — see §11.2 for upgrade path

### 8.5 `library.py` verification
- `load_creator_library(creator_id)` returns a list of `LibraryEntry` (TRIBE-pooled vec + text embedding + meta) from `cache/library/<creator_id>/*.json`
- `rank_similar(draft_brain_vec, draft_text_vec, library, top_k=3)` returns top-K with weighted cosine `α·brain + (1-α)·text` and a per-ROI breakdown
- Stacked-matrix numpy cosine over 10k entries returns in <50ms
- Returns empty `matches` + cold-start message when library size <5

### 8.6 `transcribe.py` + `text_embed.py` verification
- `transcribe(audio_path) -> str` runs Whisper-base on CPU/MPS, returns within ~1.5x realtime
- `embed_text(s) -> np.ndarray[768]` runs `nomic-embed-text-v1.5`, returns L2-normalized vector

### 8.7 `cache.py` verification
- Hero clips load at startup (`/health` reports `cache_size > 0`)
- Live request matching cached hash returns in <500ms
- Cache miss falls through to live inference

---

## §9 — API contracts

### POST `/analyze/text`
**Request:** `{text: string}`
**Response:** `{job_id: string}`
**Verification:** `curl -X POST .../analyze/text -d '{"text":"hero"}'` returns 200 with valid job_id

### POST `/analyze/audio`
**Request:** multipart with audio file
**Response:** `{job_id: string}`

### POST `/analyze/video`
**Request:** multipart with video file (or Cloudinary public_id)
**Response:** `{job_id: string}`

### GET `/stream/{job_id}` (SSE)
Events streamed in order:
1. `event: started` — `{mode, estimated_ms}`
2. `event: transcript` — `{words: [{text, start, end}]}` (audio/video only)
3. `event: brain_frame` — `{t: float, activation: number[20484]}` (one per second of input content)
4. `event: cold_zones` — `{zones: [{start, end, region}]}`
5. `event: suggestions` — `{suggestions: [...]}`
6. `event: complete` — `{}`

**Verification:** `curl -N .../stream/<id>` shows events in order

### GET `/health`
**Response:** `{status, tribe_loaded, gemma_loaded, predictor_loaded, corpus_size, cache_size, gx10_uptime_s}`
**Verification:** returns 200 with `tribe_loaded: true`, `gemma_loaded: true`, and `predictor_loaded: true`

### POST `/apply-suggestion`
**Request:** `{clip_id, suggestion_id, action: "apply"|"reject"}`
**Response:** text mode — new text + new analysis `job_id` (the rewritten paragraph re-runs through `/analyze/text`).

### POST `/predict-engagement`
**Request:** `{job_id: string, followers: int}` — `job_id` from a completed `/analyze/video`. `followers` defaults to corpus median if omitted/zero.
**Response:**
```
{
  "predicted_rate": 0.084,         // views / followers, log-space prediction exponentiated
  "predicted_rate_low": 0.061,     // 25th-percentile bootstrap CI lower bound
  "predicted_rate_high": 0.115,    //                                upper bound
  "percentile": 78,                // ranked vs. corpus engagement-rate distribution
  "interpretation": "top 25% — this is hot for your audience size",
  "corpus_size": 50,
  "predictor_version": "v0-ridge-2026-04-25"
}
```
**Verification:**
```bash
JOB=$(curl -s -X POST .../analyze/video -F file=@hero.mp4 | jq -r .job_id)
# wait for stream complete...
curl -s -X POST .../predict-engagement -H 'content-type: application/json' \
  -d "{\"job_id\":\"$JOB\",\"followers\":10000}" | jq .
# Returns 200 with predicted_rate ∈ (0, 1] and percentile ∈ [0, 100] within <100ms.
```

### POST `/library/upload`
**Request:** multipart with video file + `creator_id` form field.
**Response:** `{library_entry_id, library_size}` after TRIBE + Whisper + transcript-embed pipeline finishes (~30-60s; client should drive a progress UI from /stream/{job_id}).
**Side effect:** persists `cache/library/<creator_id>/<video_id>.json`; in-memory creator library updated.

### GET `/library/{creator_id}`
**Response:** `{creator_id, size, entries: [{video_id, uploaded_at, duration_s, thumbnail_url}]}` — metadata only, no embeddings.
**Verification:** after 5 uploads, `size == 5` and entries list has matching video_ids.

### POST `/similarity`
**Request:** `{job_id: string, creator_id: string}` — `job_id` from completed `/analyze/video`.
**Response:**
```
{
  "matches": [
    {"video_id": "...", "score": 0.91, "thumbnail_url": "...",
     "uploaded_at": "2026-03-12T18:42:00Z", "dominant_roi": "auditory",
     "roi_breakdown": {"visual": 0.62, "auditory": 0.95, "language": 0.78},
     "text_similarity": 0.81, "duration_s": 38}
  ],
  "library_size": 47,
  "creator_id": "...",
  "weighting": {"brain": 0.6, "text": 0.4}
}
```
- If `library_size < 5`: returns `{"matches": [], "library_size": N, "message": "upload at least 5 past clips"}`.
- Returns in <100ms.

**Verification:**
```bash
curl -s -X POST .../similarity -H 'content-type: application/json' \
  -d "{\"job_id\":\"$JOB\",\"creator_id\":\"hero\"}" | jq .
# After ≥5 library uploads → 3 matches with non-uniform roi_breakdown values.
```

---

## §10 — Brain visualization (Niivue)

Mesh: `fsaverage5` left + right hemispheres.

Activation mapping (TRIBE outputs `(n_timesteps, 20484)` z-scored BOLD):
- z ≤ -1: deep blue (#1a3a8a)
- -1 < z ≤ 0: gray-blue (#5a7090)
- 0 < z ≤ 1: warm gray (#a08070)
- 1 < z ≤ 2: orange (#e87b1e)
- z > 2: bright orange (#ff5500) with glow

Frame interpolation: TRIBE is 1 Hz → client renders at 30 fps. Linear interpolation per vertex with one-euro filter.

Idle: slow auto-rotate (0.1 rad/s), gentle breathing pulse on baseline activation.

**Implementation patterns:** see `@.claude/skills/niivue-rendering/SKILL.md`.

---

## §11 — Engagement prediction loop

This is the loop that turns Cortex from "pretty brain visualizer" into "tool a creator would actually open before they post."

### 11.1 Inference path (live, on each `/analyze/video`)

1. User uploads draft → `/analyze/video` → TRIBE produces `(n_timesteps, 20484)` z-scored BOLD predictions.
2. `pooling.py` reduces TRIBE output to a fixed ~25-dim feature vector by grouping vertices into 3 ROI curves (visual / auditory / language) and computing per-curve statistics — see §8.3.
3. Frontend, after `complete`, POSTs `/predict-engagement` with the user-provided follower count.
4. `predictor.py` runs `model.predict(features ++ [log(followers), duration_s])` — milliseconds.
5. Backend computes percentile rank by comparing predicted rate against `corpus.jsonl` rates.
6. Frontend renders `EngagementCard` with the number, percentile, and interpretation.

### 11.2 The predictor model — baseline + upgrade path

**v0 (hackathon build, ridge regression):**
- `sklearn.linear_model.Ridge(alpha=1.0)`
- Input: `~25 pooled TRIBE features ++ [log(followers + 1), duration_s, n_cold_zones]` → ~28 dims total
- Target: `log(engagement_rate)` where `engagement_rate = views / max(followers, 1)`
- Trains in milliseconds on 50–500 samples
- Held-out R² expected 0.05–0.25 (most short-form engagement is algorithmic noise — this is acceptable)

> **TODO (user decision):** the model class is intentionally swappable behind the `EngagementPredictor` interface in `predictor.py`. If a "tougher" regression model sounds better in the pitch, candidates ranked by hackathon-friendliness:
> - **`sklearn.ensemble.GradientBoostingRegressor`** (no extra dep) — usually +5-10% R² over ridge, "gradient-boosted regression" sounds heavier than "linear regression"
> - **`xgboost.XGBRegressor`** — adds a dep but it's the recognized name in the field, fits in seconds, "XGBoost" lands well with judges
> - **Small MLP via `sklearn.neural_network.MLPRegressor`** (or 3-layer torch model) — pitches as "small neural net," may not actually help with N≤200 samples but doesn't hurt accuracy meaningfully
> - **Don't:** transformer over raw frames, fine-tune TRIBE itself, anything that needs a GPU at predict time
>
> Whichever the user picks, the swap is one constructor call in `predictor.py`. Pick after the v0 ridge baseline is wired and demonstrably working — don't tune the model before the pipeline is end-to-end.

### 11.3 Training corpus (`corpus.jsonl`)

One JSON object per line:
```json
{"video_id": "yt:abc123", "source": "youtube_shorts", "duration_s": 28.0,
 "followers": 12500, "views": 84000, "likes": 7200, "comments": 410,
 "engagement_rate": 6.72, "tribe_features": [...25 floats...],
 "ingested_at": "2026-04-25T08:30:00Z", "predictor_version": null}
```

- Pre-hack PH-I seeds 50 videos across 5 niches.
- Each batch ingest appends rows; `fit_predictor.py` reads the full file and re-trains.
- The corpus is also the percentile-rank reference at inference time (no separate stats blob).

### 11.4 Offline ingest (`scripts/ingest_shorts.py`)

```
yt-dlp --skip-download -j "<url>"   # metadata
yt-dlp -f mp4 -o "<id>.mp4" "<url>" # video
↓
TRIBE.predict(video_path) → (T, 20484)
↓
pooling.pool_tribe_output(...) → 25-dim vector
↓
append row to corpus.jsonl
```

Demo path = `yt-dlp` + manual URL list. **Real path (spec'd in §11.7) = a single NemoClaw agent running in the uvicorn lifespan, discovering URLs autonomously via `yt-dlp ytsearch20:<query>` (no manual seed list), targeting predictor gaps, refitting in-process with R²-rollback. Replaces the cron entirely.** The agent is the demo's "the box gets smarter on its own" line — and the same agent rotates a trending iteration every 6 cycles to power §11.8 (inspiration feed).

### 11.5 Text-mode rewrite suggestions

(Carried over from the original §11; this is independent of engagement prediction and stays scoped to text mode.)

1. Text analysis returns `cold_zones` (sentences where engagement dropped).
2. User clicks a cold sentence → `SuggestionPanel` opens.
3. Gemma rewrites the sentence, preserving the factual claim.
4. User clicks **Apply** → frontend POSTs `/apply-suggestion`, substitutes the rewrite locally, and re-runs `/analyze/text` on the new paragraph.
5. Brain re-pulses; the previously-cold sentence now warms.

**Failure modes:**
- Gemma returns empty / unusable rewrite → frontend keeps the original, surfaces a soft message.
- `/apply-suggestion` returns 5xx → frontend logs and shows the local rewrite anyway.

**Verification:** apply a suggestion on a hero paragraph → re-render in <12s with visible warming on the formerly-cold sentence.

### 11.6 Creator library + originality search

The 128 GB unified memory turns into a feature here: a creator's entire short-form back-catalog can live in RAM as TRIBE features + transcript embeddings, and we can tell them, in <100ms, *"the brain pattern of this draft is 91% similar to your post from March 12 — you've made this video before."*

This is the second pillar of the pitch. Engagement prediction asks *"will this work?"*; originality search asks *"are you repeating yourself?"* Both are creator-facing, both are GX10-native, both share the same TRIBE pipeline.

**Library lifecycle:**
1. Creator uploads N (≥5, gated) past Shorts/Reels/TikToks via the same uploader.
2. For each: Phase 1 caches the mp4 + meta locally (no download from external platforms — files come from the creator's drive). Phase 2 runs TRIBE + transcribes the audio with Whisper-base + embeds the transcript with `nomic-embed-text-v1.5`.
3. Each library entry persists as `cache/library/<creator_id>/<video_id>.json`:
   ```json
   {"video_id": "...", "uploaded_at": "...", "duration_s": 42,
    "tribe_pooled": [...21 floats...],
    "tribe_per_roi_curve": [...optional finer signal...],
    "transcript": "...", "text_embedding": [...768 floats...],
    "thumbnail_url": "..."}
   ```
4. Library entries are loaded into a per-creator in-memory dict at startup (or on first request after upload) — no vector DB. Brute-force cosine over <10k vectors is <50ms in numpy.

**Live similarity flow (`POST /similarity`):**
1. Frontend, after a draft `complete` SSE on `/analyze/video`, POSTs `{job_id, creator_id}`.
2. Backend pulls cached `tribe_pooled` + transcript embedding for the draft job.
3. For each library entry: `score = α · cos(brain_draft, brain_lib) + (1-α) · cos(text_draft, text_lib)` where α defaults to `SIMILARITY_BRAIN_WEIGHT = 0.6`.
4. Rank, return top 3 with per-ROI similarity breakdown so the UI can say *"your auditory cortex pattern matches this clip — you tend to reach for the same audio hooks."*
5. Response shape:
   ```json
   {"matches": [
     {"video_id": "...", "score": 0.91, "thumbnail_url": "...",
      "uploaded_at": "...", "dominant_roi": "auditory",
      "roi_breakdown": {"visual": 0.62, "auditory": 0.95, "language": 0.78},
      "text_similarity": 0.81}
   ], "library_size": 47, "creator_id": "..."}
   ```

**Cold-start gate:** library < `SIMILARITY_MIN_LIBRARY_SIZE` (5) → endpoint returns `{matches: [], library_size: N, message: "upload at least 5 past clips"}`. Frontend hides the panel.

**Frontend (`SimilarityPanel.tsx`):** below the EngagementCard, three thumbnail cards with similarity score + ROI breakdown chip. Click → opens the matched clip in a side drawer. Sub-100ms render after the prediction lands.

**Memory budget:** 21 floats (84B) + 768-dim text embedding (3KB) + transcript (~5KB) + thumbnail URL ≈ 8KB per clip. 10k-clip library = 80MB. The 128GB box laughs.

**Verification:**
- Upload 5+ hero library clips → POST /similarity for a fresh draft → returns 3 matches with non-trivial ROI breakdown variance (not all 1.0, not all 0.0).
- Library size 0–4 → endpoint returns the cold-start message; frontend hides panel.
- Same draft uploaded twice → top match is itself with score ~1.0 (sanity check).

### 11.7 Active-learning corpus curator (idle-time agent on GX10)

The GX10 is idle ≥95% of the time outside live demo windows. Instead of letting it sit, **a single NemoClaw agent runs an active-learning loop** that grows the engagement-prediction corpus on its own — and chooses *what* to ingest based on where the current ridge model is weakest. NemoClaw (NVIDIA NeMo-stack agent framework) is the right choice for this hackathon: the GX10 is Blackwell silicon, the ASUS challenge is partnered with NVIDIA, and "we run a NemoClaw agent on the Blackwell box" is a one-line judging signal that ties the hardware to the agent layer.

**One agent, two iteration types (rotating).** Same loop, same TRIBE pipeline; only the terminal step differs:

| Iteration type | Frequency | Terminal step |
|---|---|---|
| **Corpus** (active-learning) | 5 of every 6 | Append features → `corpus.jsonl`, refit ridge, R²-rollback if regressed |
| **Trending** (inspiration pool) | 1 of every 6 | Write features → `cache/trending/<yyyy-mm-dd>/<id>.json` (powers §11.8) |

Splitting into two agents would mean two priority gates fighting one TRIBE handle, two log files, two failure modes — for zero benefit (TRIBE GPU is single-tenant). One coroutine, one log, one status endpoint, one kill switch.

**The loop** (one iteration ≈ 30–60 min, paused entirely when any job is in flight):

```
0. Iteration type
   type = "trending" if iter_count % 6 == 5 else "corpus"

1. Priority gate
   if any _JOBS in PROCESSING/STREAMING:  sleep(30); continue

2. Query selection (see "How the agent knows what to scrape" below)
   queries = pick_queries(type, corpus, predictor, query_pool)

3. URL discovery (yt-dlp ytsearch — no manual seed list)
   for q in queries:
     urls += yt-dlp(f"ytsearch20:{q}", metadata_only=True)
   filter: duration ≤ 180s, view_count > 1000, is_short, not in corpus or trending
   pick top N (3-5) matching the gap criteria

4. Feature extractor (existing pipeline)
   yt-dlp -f mp4 → tribe.predict → pooling.pool_tribe_output (+ Whisper + nomic for trending)
   delete the mp4 (raw video never retained — same rule as §11.6)

5. Terminal step (depends on iteration type)
   if type == "corpus":
     append row to corpus.jsonl
     refit predictor in-process; if R² regresses > 0.02 → rollback pickle, mark rows excluded=true
   else:  # trending
     write to cache/trending/<yyyy-mm-dd>/<video_id>.json (date-partitioned, 7d TTL)

6. Log + bookkeeping
   append to cache/curator_log.jsonl
   if iteration produced a high-engagement clip: feed transcript → Gemma → enrich query pool
```

**How the agent knows what to scrape (no `seed_urls.txt` ever):**

URL discovery is fully autonomous via `yt-dlp ytsearch20:<query>` — yt-dlp's search prefix takes any query string and returns the top 20 matching Shorts URLs with metadata. No API key, no manual list. The only state the agent needs is *what to search for*, which comes from three sources used in priority order:

1. **Bootstrap queries** (cold start: predictor R² < 0.05 OR corpus < 100 rows)
   - Hardcoded `BOOTSTRAP_QUERIES` constant in `curator_gap.py` — ~12 diverse niches: `cooking shorts`, `fitness shorts`, `explainer shorts`, `comedy shorts`, `beauty tutorial shorts`, `gaming clip shorts`, `dance shorts`, `asmr shorts`, `pitch shorts`, `lifestyle shorts`, `science shorts`, `motivation shorts`.
   - Sampled uniformly until the predictor has enough signal to identify gaps.

2. **Gap-driven queries** (warm predictor)
   - Gap-finder emits a `GapDescriptor`: per-bin `predicted-rate variance × (1 / bin density)` over the corpus → identify the weakest bin.
   - Gemma 2B prompt: *"You are picking YouTube Shorts to fill a gap in a training set. Gap: `<descriptor>`. Output 5 short search queries, one per line, no commentary."* → 5 queries.
   - Example gap → queries: `"high-engagement (>20%) + heavy auditory ROI"` → `["viral asmr cooking shorts", "soundtrack hooks tiktok shorts", "audio meme shorts trending", "voiceover storytelling shorts", "music drop shorts"]`.

3. **Self-supervised query expansion** (continuous)
   - After every successful corpus iteration, Gemma summarizes the transcripts of top-quartile engagement clips into 1-2 candidate queries (*"these high-engagement clips are all about X — generate 2 search queries on that theme"*).
   - Appended to `cache/curator_query_pool.jsonl` (rolling cap of 200, FIFO).
   - Sampled with low probability (~10%) per iteration alongside bootstrap/gap queries — the agent learns its own search vocabulary over time without ever hardcoding niche-specific terms.

**Trending iteration queries** rotate across a fixed list — `["#shorts trending today", "#shortsoftheday viral", "#fyp shorts", "trending shorts this week", "viral shorts today"]` — same `ytsearch20:` mechanism, no separate API.

**State:**
- Driver: `gx10/brain/curator.py` — long-running asyncio coroutine started by uvicorn lifespan, stopped on shutdown.
- Append-only log: `gx10/cache/curator_log.jsonl` — one row per iteration `{ts, type, queries, n_added, r2_before, r2_after, excluded}`.
- Query pool: `gx10/cache/curator_query_pool.jsonl` — self-supervised query expansions (capped at 200).
- Status endpoint: `GET /curator/status` → `{running, last_iter_at, last_iter_type, corpus_size, trending_pool_size, last_r2, paused_for_jobs, kill_switch}`. The frontend StatusChip surfaces `last_r2` + `corpus_size` + `trending_pool_size` on hover.
- Kill switch: `touch cache/curator.disabled` → loop exits at next iteration.

**Coordination with live inference:**
- Single shared `tribe_model` instance — curator does **not** load a second copy.
- Iteration begins with a memory-release call (Apple unified-memory equivalent of `torch.cuda.empty_cache`).
- `if any _JOBS in PROCESSING/STREAMING: sleep(30)` is the only synchronization. No locks.

**Failure modes:**
- yt-dlp breaks (rate-limit or schema change) → log + skip iteration. Don't crash the server.
- Source returns nothing → fall back to a static seed query list at `cache/curator_seed_queries.json`.
- TRIBE OOM → release memory, halve `n_per_iter`, retry next iteration.
- Predictor R² regression → keep the rows but mark `excluded=true`, roll back the pickle.

**Verification:**
- Start curator with 50-row seed → after 4 iterations corpus grows by ≥ 40 rows; log shows `r2_after > r2_before` on at least 2 iterations.
- Start a `/analyze/video` job mid-iteration → curator pauses within 30s; live request completes in baseline latency (no slowdown vs. curator-disabled run).
- `touch cache/curator.disabled` → `GET /curator/status` returns `running: false` within one iteration.

**Demo line:** *"the box gets smarter on its own — even when you're not using it."*

### 11.8 Trending inspiration feed (the third pillar)

Engagement prediction asks *"will this work?"*. Originality search asks *"am I repeating myself?"*. The inspiration feed answers the third creator question: **"what should I make next?"**

Same TRIBE pipeline + same cosine fusion as §11.6, different candidate pool. The curator (§11.7) is the harvester; this section spec'es the consumer side.

**v1 scope: YouTube Shorts only.** TikTok and Reels lack public trending APIs and require third-party aggregators that break weekly. Out for v1.

**Pool lifecycle:**
1. The same NemoClaw agent from §11.7 — running a "trending" iteration once every 6 iterations — hits `yt-dlp ytsearch20:<trending-query>` rotating across `["#shorts trending today", "#shortsoftheday viral", "#fyp shorts", ...]`. No separate agent, no manual URL list.
2. For each candidate: TRIBE-pool + Whisper transcript + nomic embedding. Same shape as a library entry, **stored at `cache/trending/<yyyy-mm-dd>/<video_id>.json`** (date-partitioned for easy expiry).
3. Pool TTL: 7 days. A nightly cleanup deletes folders older than 7 days from `cache/trending/`.
4. Memory budget: ~100 trending clips × 8KB ≈ 800KB. Negligible.

**Inference flow (`GET /inspiration/{creator_id}`):**
1. Load creator library (same in-memory dict as §11.6).
2. Compute creator **centroid**:
   - `centroid_brain` = L2-normalized mean of `tribe_pooled` across library entries.
   - `centroid_text` = L2-normalized mean of `text_embedding` across library entries.
3. For each trending pool entry: `score = α · cos(centroid_brain, brain_pool) + (1-α) · cos(centroid_text, text_pool)`, α = 0.6 (reuses `SIMILARITY_BRAIN_WEIGHT`).
4. Rank, return top-K with thumbnail + source URL + per-ROI breakdown.
5. Response shape:
   ```json
   {"recommendations": [
     {"video_id": "...", "score": 0.78, "thumbnail_url": "...",
      "source_url": "https://youtube.com/shorts/...",
      "uploaded_at": "...", "creator_handle": "...",
      "view_count": 1240000, "engagement_rate": 0.184,
      "dominant_roi": "auditory",
      "roi_breakdown": {"visual": 0.64, "auditory": 0.91, "language": 0.72}}
   ], "library_size": 47, "trending_pool_size": 96, "centroid_age_s": 3600}
   ```
6. Cold-start: library < `SIMILARITY_MIN_LIBRARY_SIZE` (5) → `{recommendations: [], library_size: N, message: "upload at least 5 past clips"}`.

**Source-URL hygiene:**
- Store the canonical Shorts URL — never the mp4. Raw video deleted post-ingest (same rule as §11.7).
- Thumbnails: store the YouTube-hosted URL (`https://i.ytimg.com/vi/<id>/hqdefault.jpg`). If the source video is deleted, the thumbnail 404s gracefully — the UI handles `onError` with a placeholder.

**Frontend (`InspirationFeed.tsx` on `/library`):**
- Section below the past-clips table — **"trending Shorts that match your style"**.
- 3 cards horizontally: thumbnail + dominant-ROI chip + similarity score (e.g., *"78% match · auditory"*).
- Each card links out to the source URL in a new tab.
- Hidden during cold-start.

**Verification:**
- Trending pool ≥ 50 entries + library ≥ 5 → `GET /inspiration/demo` returns 3 cards with scores in 0.4–0.9 range (no all-1.0 self-matches because trending pool is disjoint from creator library).
- Library = 0 → cold-start message; frontend hides the section.
- 7-day-old `cache/trending/<date>/` folder → nightly cleanup deletes it; `cache/trending/` shows ≤ 7 dated subfolders.

**Why this is the third pillar:** the same TRIBE pooling + cosine math powers all three creator questions. One inference pipeline, three demo lines: *"is this good? have I made it before? what should I make next?"*

---

## §12 — Cache + fallback layer

**Hero clip cache:** `prerender_heroes.py` populates `gx10/cache/hero_*/*.json` before hackathon. Loaded into memory at server startup.

**Live request cache:** hash incoming content → check cache → fall back to live TRIBE if miss. Live results cached for session.

**Failure fallback:** every "live" frontend path wraps in try-catch → on backend error or >60s timeout, swap in cached hero with soft message. Judges never see a broken state.

**Verification:** kill the GX10 mid-request → frontend shows cached fallback within 5s with `session timed out, here's a saved analysis` message.

---

## §13 — Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | TRIBE env setup fails (NumPy ABI, LLaMA gating, CUDA) | High | Catastrophic | Pre-hack PH-A/PH-B by Wed; pivot to 3D Movement Coach if not working by EOD Wed |
| R2 | Niivue mesh rendering buggy / shader issues | Medium | High | Prototype in PH-D; have fallback PNG-rotation video if shader fails |
| R3 | Tailscale blocked at Pauley venue Wi-Fi | Medium | High | Phone hotspot fallback for laptop↔GX10 |
| R4 | Gemma suggestion quality mid for short content | Medium | Medium | Hand-curate 5-10 prompt examples; hardcoded fallback per cold-zone type |
| R6 | TRIBE output noisy on judge-uploaded clips | Medium | Medium | Tooltip on upload: "best with naturalistic video and conversational text"; pivot to hero clips |
| R7 | GX10 dies mid-demo | Low | Catastrophic | Backup laptop with cortexlab Streamlit dashboard as full fallback |
| R9 | Engagement model R² is near zero — predictions don't track reality | Medium | Medium | Frame the demo around *"the brain features are predictive of variance, here's the honest R²"* — judges respect transparency. Fallback: hardcode "predicted top-quartile / median / bottom-quartile" buckets if the regressor goes haywire. |
| R10 | yt-dlp blocked or rate-limited mid-ingest | Medium | Low | PH-I runs pre-hack; the corpus is on disk before the demo. If we want to *demo* live ingest, have a 3-video URL list pre-tested. |
| R11 | Engagement metric in corpus is mostly "the algorithm pushed it" not "viewers liked it" | Inherent | Low | Frame as *"predicting algorithmic engagement"* — that's literally what creators want to optimize. Do not claim we predict *quality*. |
| R12 | Whisper / nomic-embed model load adds startup latency (~30s extra) | Medium | Low | Lazy-load on first `/library/upload` instead of at server boot. Upload UX already has a progress bar so the cold-load tax hides inside it. |
| R13 | Creator library top match is always trivially-similar (same speaker → identical voice features dominate) | Medium | Medium | Brain weight α=0.6 (not 1.0) keeps text similarity from dominating; if matches still feel uniform, expose the α slider in DebugOverlay so we can re-tune live. |
| R14 | TRIBE 21-dim pooled vector is too coarse for similarity (everything looks similar) | Medium | Medium | Fall back to the per-ROI time-curve embeddings (`tribe_per_roi_curve` in `LibraryEntry`) — concatenated visual+auditory+language curves are 180-540 dims and discriminative enough to break ties. |

---

## §14 — Demo script (verbatim, for rehearsal)

**Beat 1 — open with text (15s).**
Already on Text tab. Pre-loaded paragraph. Click `Diagnose`.
> *"Most creators ship work and wait two weeks for analytics to know if it landed. We don't. Watch."*

5s render. Heatmap underlines. Two sentences orange, middle sentence blue.
> *"Three sentences in. The model says the average reader checked out on the middle one."*

Click cold sentence → Gemma suggestion → Apply → re-render in 5s → warm.
> *"Five-second iteration. Edit, see the brain, edit again."*

**Beat 2 — switch to video (25s, the spectacle).**
Hit Video tab. Pre-rendered 30s hero clip. Hit play. Brain syncs. Around 0:18, language region visibly dims.
> *"Right there. Eighteen seconds. They lost the average viewer."*

Tap the red cold-zone band → player jumps to 0:18 → re-watch with the brain showing exactly which region dropped.

**Beat 3 — engagement prediction (35s, the money beat).**
Engagement card animates in next to the brain.
> *"And here's the part our hardware lets us do that no laptop can. We trained a model on real public Shorts — 50 of them so far, the offline scraper agent on the box adds more every night. We took TRIBE's brain prediction, pooled it into a feature vector, paired each one with the actual view count and the uploader's follower count, and learned what brain patterns correlate with engagement."*

Point at the card.
> *"This clip's predicted engagement rate is 8.4% — that's the 78th percentile of our corpus for an account this size. If you're sitting on this draft right now, you ship it."*

Type a different follower count into the box. Card re-renders instantly.
> *"Change the audience size, the percentile updates client-side. The brain features don't change — only the comparison set does."*

**Beat 3.5 — originality search (20s, the hardware flex).**
Below the engagement card, three thumbnails of the creator's past clips appear with similarity scores.
> *"And because the box has 128 gigs, we can keep their entire back-catalog in memory as TRIBE features. So when they upload this draft, we can also tell them — instantly — which of their past videos has the most similar brain pattern. They've already made this video. Or they haven't, and they're original. Either way, they know before they hit post."*

Tap the top match → side drawer slides in showing it's a 91% brain match, especially in the auditory cortex.
> *"Same hooks. Same audio rhythm. The brain doesn't lie — they're recycling."*

**Beat 4 — switch to audio (15s).**
Hit Audio tab. Pre-rendered podcast clip. Brain pulses but only auditory + language regions.
> *"Same diagnostic, audio only. The model knows when a speaker loses themselves."*

**Beat 5 — hand the tablet over (45s).**
> *"Try one. Email, tweet, voice memo, video — whatever you've got."*

Most judges paste text first. They watch one of their own sentences underline blue. They react.

**Beat 6 — close (20s).**
Step back, gesture at GX10.
> *"Same engine, three surfaces, all on the box behind me. TRIBE came out a month ago — most teams couldn't load it, it needs 30 gigs of GPU memory. We have 128. The brain prediction, the engagement model, the corpus, and the scraper agent that re-trains it nightly all live here. Your draft never leaves the box. Whatever you ship, this is the first tool that tells you if it'll land before your audience does."*

Slide tablet back. Walk three steps away.

**Total runtime:** ~3 minutes.

---

## §15 — Failure-mode pivots

| If this breaks at hour N... | Pivot to... |
|---|---|
| TRIBE env still broken at Wed EOD pre-hack | **Abandon Cortex.** Pivot to 3D Movement Coach. |
| Niivue shader broken at hour 14 | Replace BrainMonitor with rotating PNG video of pre-rendered brain animation |
| Gemma suggestions weak at hour 16 | Hand-written suggestion library indexed by cold-zone region |
| Engagement predictor R² ≤ 0 at hour 16 | Drop to 3-bucket classifier ("top-quartile / median / bottom-quartile") via simple thresholds on `n_cold_zones` and `language.fraction_below_zero`. Card still renders a number — just rounded into a bucket. Honest framing in pitch. |
| `corpus.jsonl` < 30 rows by hour 14 | Skip percentile rank, show only the predicted rate; mention "trained on N=20 — pipeline scales, the seed set is small for the demo." |
| Tailscale blocked at venue | Phone hotspot dedicated to laptop↔GX10 |
| GX10 unavailable | Backup laptop running cortexlab Streamlit dashboard |

---

*Last updated: pre-hackathon. See `@docs/CLAUDE.md` for project rules, `@docs/TASKS.md` for work queue, `@.claude/skills/` for domain-specific patterns.*
