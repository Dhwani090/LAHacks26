# TASKS.md — Cortex Work Queue

> **Per-task contract:** every task includes a **Verification command** (a literal Bash one-liner) and an **Out-of-scope** list (files Claude must NOT touch). Claude Code reads `@docs/CLAUDE.md` §6 before starting any task and outputs a Plan first.
>
> **One task per session.** `/clear` between tasks. Mark ✅ only when verification passes.
>
> **Skills:** if a task touches TRIBE inference or Niivue rendering, load the matching skill from `@.claude/skills/` first.

---

## Pre-Hackathon — week of April 20 (MUST be done by Wed April 23 EOD)

> **GATE:** if any ⬜ here is still red on Wed EOD, **abandon Cortex** and pivot to 3D Movement Coach.

### PH-A · LLaMA license acceptance
- **Owner:** Anyone (do this Monday April 20)
- **Action:** llama.meta.com → accept license → request access at huggingface.co/meta-llama/Llama-3.2-3B
- **Verification:** HF dashboard at huggingface.co/settings/gated-repos shows "approved" for `meta-llama/Llama-3.2-3B`
- **Out of scope:** any code, any other licenses

### PH-B · TRIBE env on GX10 (initializer session)
- **Owner:** strongest engineer
- **References:** `@.claude/skills/tribe-inference/SKILL.md` (read FIRST), https://github.com/facebookresearch/tribev2, https://www.datacamp.com/tutorial/tribe-v2-tutorial (gotchas)
- **Files to create:** `cortex/gx10/scripts/setup_env.sh`, `cortex/gx10/requirements.txt`, `cortex/gx10/init.sh` (initializer script per Anthropic's harness pattern), `cortex/gx10/progress.txt` (running log of what subsequent sessions have done)
- **Action sequence:**
  1. SSH to GX10. `conda create -n cortex python=3.11 -y && conda activate cortex`
  2. `pip install "numpy<2.1"` BEFORE installing tribev2 (NumPy 2.x ABI breaks the build)
  3. `huggingface-cli login` with HF token
  4. `export HF_HUB_DOWNLOAD_TIMEOUT=300` in `~/.bashrc`
  5. `pip install "tribev2[plotting] @ git+https://github.com/facebookresearch/tribev2.git"`
  6. `pip install cortexlab-toolkit transformers ffmpeg-python fastapi uvicorn sse-starlette pydantic`
  7. Pre-download LLaMA: `python -c "from huggingface_hub import snapshot_download; snapshot_download('meta-llama/Llama-3.2-3B')"`
- **Verification:**
  ```bash
  python -c "from cortexlab.inference.predictor import TribeModel; m = TribeModel.from_pretrained('facebook/tribev2', device='auto'); print('LOADED')"
  ```
  Must print `LOADED` without errors.
- **Out of scope:** anything beyond environment setup; no app code yet

### PH-C · TRIBE end-to-end inference test
- **Owner:** PH-B owner
- **References:** `@.claude/skills/tribe-inference/SKILL.md`, `@cortex/gx10/init.sh`
- **Files to create:** `cortex/gx10/scripts/test_inference.py`, `cortex/spikes/tribe_latency.md`
- **Action:** run TRIBE on a 30s test video using the pattern from `tribe_demo.ipynb`. Assert output shape, log wall-clock latency.
- **Verification:**
  ```bash
  python cortex/gx10/scripts/test_inference.py && cat cortex/spikes/tribe_latency.md
  ```
  Must print prediction shape `(N, 20484)` for some N, and latency.md must contain a recorded number.
- **Out of scope:** caching, FastAPI, frontend

### PH-D · Next.js + niivue-react scaffold
- **Owner:** frontend lead
- **References:** `@.claude/skills/niivue-rendering/SKILL.md` (read FIRST), https://niivue.com/docs/
- **Files to create:** `cortex/web/` (full Next.js project), `cortex/web/app/page.tsx`, `cortex/web/app/components/BrainMonitor.tsx` (placeholder)
- **Action:**
  1. `npx create-next-app@latest cortex/web --typescript --tailwind --app --src-dir`
  2. `cd cortex/web && npm install @niivue/niivue niivue-react framer-motion @cloudinary/react`
  3. Render the demo mesh from `https://niivue.github.io/niivue-demo-images/BrainMesh_ICBM152.lh.mz3` with auto-rotate
- **Verification:**
  ```bash
  cd cortex/web && npm run dev
  # Open localhost:3000 in browser, see rotating brain
  ```
- **Out of scope:** any analysis logic, any backend integration

### PH-E · Pre-render 5 video hero clips
- **Owner:** PH-B owner
- **References:** `@.claude/skills/tribe-inference/SKILL.md`
- **Files to create:** `cortex/gx10/scripts/prerender_heroes.py`, `cortex/gx10/cache/hero_video/*.json`
- **Hero clips:** Khan Academy 30s, TikTok ad 30s, podcast clip 30s, startup pitch 30s, movie trailer 30s
- **Action:** run TRIBE on each. Save outputs as JSON: `{transcript, brain_frames, engagement_curves, cold_zones}`
- **Verification:**
  ```bash
  ls cortex/gx10/cache/hero_video/*.json | wc -l
  # Must output: 5
  python -c "import json; d = json.load(open('cortex/gx10/cache/hero_video/khan.json')); assert 'brain_frames' in d; print(len(d['brain_frames']))"
  # Must print integer >= 25
  ```
- **Out of scope:** audio or text caching (separate tasks)

### PH-F · Pre-render 5 audio hero clips
- **Owner:** PH-B owner
- **Files to create:** `cortex/gx10/cache/hero_audio/*.json`
- **Verification:**
  ```bash
  ls cortex/gx10/cache/hero_audio/*.json | wc -l
  # Must output: 5
  ```

### PH-G · Pre-render 5 text examples
- **Owner:** PH-B owner
- **Files to create:** `cortex/gx10/cache/hero_text/*.json`
- **Verification:**
  ```bash
  ls cortex/gx10/cache/hero_text/*.json | wc -l
  # Must output: 5
  ```

### PH-I · Build the 50-video YT Shorts seed corpus
- **Owner:** PH-B owner (model owner)
- **References:** `@docs/PRD.md#§11.3,§11.4`, `@.claude/skills/engagement-prediction/SKILL.md` (load FIRST)
- **Files needed:** `cortex/gx10/scripts/seed_urls.txt` (hand-curated — 10 URLs each across 5 niches: cooking / explainer / pitch / comedy / fitness). Output lands in `cortex/gx10/cache/corpus.jsonl`.
- **Two ingest paths — pick one:**

  **Path A — One-machine (GX10 has yt-dlp + TRIBE):**
  1. `pip install yt-dlp scikit-learn`
  2. `python scripts/ingest_shorts.py scripts/seed_urls.txt`
     - For each URL: yt-dlp metadata + mp4 → TRIBE → pool → append row
  3. Idempotent: re-running skips ids already in `corpus.jsonl`

  **Path B — Mac+GX10 split (recommended when the GX10 is busy):**
  1. **On the Mac**, while the GX10 is occupied:
     ```bash
     pip install yt-dlp
     python scripts/download_shorts.py scripts/seed_urls.txt --out-dir downloads/
     ```
     Writes `<id>.mp4` + `<id>.meta.json` per URL. No TRIBE needed. Idempotent.
  2. **Transfer:**
     ```bash
     rsync -avz --progress downloads/ gx10:~/cortex_downloads/
     ```
     ~750 MB for 50 clips → typically <2 min over Tailscale WireGuard.
  3. **On the GX10**, when free:
     ```bash
     python scripts/process_downloads.py --in-dir ~/cortex_downloads/
     ```
     For each `<id>.mp4` + sidecar JSON: TRIBE → pool → append. Skips ids already in corpus.
- **Verification:**
  ```bash
  wc -l cortex/gx10/cache/corpus.jsonl  # Must be ≥ 50
  python -c "
  import json
  rows = [json.loads(l) for l in open('cortex/gx10/cache/corpus.jsonl')]
  rates = sorted(r['engagement_rate'] for r in rows)
  print(f'n={len(rows)} min={rates[0]:.3f} median={rates[len(rates)//2]:.3f} max={rates[-1]:.3f}')
  print(f'feature dims: {len(rows[0][\"tribe_features\"])}')
  "
  # n ≥ 50, feature dims = 21, sane min/median/max.
  ```
- **Out of scope:** the predictor itself (PH-J), live ingest endpoint, NemoClaw curator (Phase R)

### PH-J · Fit v0 engagement predictor (ridge)
- **Owner:** PH-B owner
- **References:** `@docs/PRD.md#§11.2`, `@.claude/skills/engagement-prediction/SKILL.md`
- **Files to create:** `cortex/gx10/scripts/fit_predictor.py`, `cortex/gx10/cache/engagement_predictor.pkl`, `cortex/gx10/spikes/predictor_metrics.md`
- **Action:**
  1. Read `corpus.jsonl`. Build feature matrix `X = [tribe_features ++ log(followers+1) ++ duration_s ++ n_cold_zones]`, target `y = log(engagement_rate)`.
  2. 80/20 train/test split (deterministic seed). Fit `sklearn.linear_model.Ridge(alpha=1.0)`.
  3. Print and save `R²` on held-out + a sample prediction vs. actual table.
  4. Pickle the fitted model + the feature-column order to `engagement_predictor.pkl`.
- **Verification:**
  ```bash
  python cortex/gx10/scripts/fit_predictor.py
  cat cortex/gx10/spikes/predictor_metrics.md   # Contains held-out R², sample predictions
  test -f cortex/gx10/cache/engagement_predictor.pkl
  ```
  R² ≥ 0 (yes, even slightly negative on tiny corpora is fine — log it honestly). Pickle exists.
- **Out of scope:** the `/predict-engagement` endpoint (P2-06); model upgrades — see PRD §11.2 TODO

---

## Phase 0 — Hours 0–1 — Setup Spikes (PARALLEL, 4 owners)

> **Gate:** all four ✅ before anyone writes feature code.

### P0-A · Backend skeleton up on GX10
- **Owner:** lead engineer
- **References:** `@docs/PRD.md#§3,§8,§9`, `@cortex/gx10/init.sh` (from PH-B)
- **Files to create:** `cortex/gx10/brain/main.py`, `models.py`, `config.py`, `cortex/gx10/scripts/01_start_brain.sh`
- **Action:** FastAPI app with all analysis endpoints returning hardcoded stubs. TRIBE + Gemma loaded at startup.
- **Verification:**
  ```bash
  bash cortex/gx10/scripts/01_start_brain.sh &
  sleep 60  # model load time
  curl -s http://localhost:8080/health | jq .
  # Must return: {"status":"ok","tribe_loaded":true,"gemma_loaded":true,...}
  ```
- **Out of scope:** real inference (use stubs)

### P0-B · Next.js shell with three tabs
- **Owner:** frontend lead
- **References:** `@docs/PRD.md#§7`
- **Files to create:** `cortex/web/app/page.tsx`, `app/components/ModeTabs.tsx`, `app/components/BrainMonitor.tsx`
- **Action:** mode toggle (Text/Audio/Video), placeholder content per surface, Niivue brain on right
- **Verification:**
  ```bash
  cd cortex/web && npm run typecheck && npm run dev
  # Manual: clicking tabs swaps surface, brain visible on right
  ```
- **Out of scope:** any backend integration, any real analysis logic

### P0-C · Tailscale at venue verification
- **Owner:** anyone
- **References:** `@docs/PRD.md#§13-R3`
- **Files to create:** `cortex/spikes/network_results.md`
- **Action:** confirm laptop↔GX10 over Pauley venue Wi-Fi AND phone hotspot fallback
- **Verification:**
  ```bash
  curl -s http://<gx10-tailnet-ip>:8080/health
  # Must return 200 over both venue Wi-Fi and hotspot
  ```

### P0-D · Cache layer + fallback infrastructure
- **Owner:** anyone
- **References:** `@docs/PRD.md#§12`
- **Files to create:** `cortex/gx10/brain/cache.py`, `cortex/web/app/lib/cache.ts`
- **Action:** backend loads all hero JSON at startup; frontend swap-to-cached-hero on any backend failure or >60s timeout
- **Verification:**
  ```bash
  # Start backend, then kill it
  curl -s http://<gx10-ip>:8080/health  # should fail
  # Open frontend, click Diagnose on hero text
  # Frontend should show cached result within 5s with "session timed out" notice
  ```

---

## Phase 1 — Hours 1–6 — Text Mode Vertical Slice (SERIAL)

> **Goal:** text mode end-to-end. Paste → heatmap → click cold zone → apply suggestion → brain re-pulses.
> **Gate:** demo Beat 1 (text mode) runs cleanly 3× in a row.

### P1-01 · Backend `/analyze/text` with TRIBE wrapper
- **References:** `@.claude/skills/tribe-inference/SKILL.md` (REQUIRED), `@docs/PRD.md#§6.1,§8.1,§9`
- **Files to modify:** `cortex/gx10/brain/main.py`, `cortex/gx10/brain/tribe.py`
- **Verification:**
  ```bash
  curl -X POST http://<gx10-ip>:8080/analyze/text \
    -H 'Content-Type: application/json' \
    -d '{"text":"<hero text from cache>"}' \
    | jq .job_id
  # Must return valid UUID. With hero text, response time <500ms (cache hit).
  ```
- **Out of scope:** audio, video; suggestions (separate task P1-06)

### P1-02 · Backend SSE brain frame streaming
- **References:** `@docs/PRD.md#§9,§10`
- **Files to create:** `cortex/gx10/brain/streaming.py`
- **Files to modify:** `cortex/gx10/brain/main.py`
- **Verification:**
  ```bash
  JOB_ID=$(curl -s -X POST http://<gx10-ip>:8080/analyze/text -d '{"text":"hero"}' | jq -r .job_id)
  curl -N http://<gx10-ip>:8080/stream/$JOB_ID
  # Must show events in order: started → brain_frame... → cold_zones → suggestions → complete
  ```

### P1-03 · Frontend Text surface UI
- **References:** `@docs/PRD.md#§6.1,§7`
- **Files to create:** `cortex/web/app/components/TextSurface.tsx`, `app/lib/brainClient.ts`
- **Verification:**
  ```bash
  cd cortex/web && npm run typecheck
  # Manual: paste hero text → click Diagnose → state updates with response
  ```
- **Out of scope:** brain visualization (P1-04), heatmap (P1-05)

### P1-04 · BrainMonitor wired to SSE
- **References:** `@.claude/skills/niivue-rendering/SKILL.md` (REQUIRED), `@docs/PRD.md#§7.1,§10`
- **Files to modify:** `cortex/web/app/components/BrainMonitor.tsx`
- **Files to create:** `cortex/web/app/lib/colormap.ts`
- **Verification:**
  ```bash
  cd cortex/web && npm run typecheck
  # Manual: during text analysis, brain visibly pulses through activation states
  # Frame interpolation must be smooth (no visible 1Hz steps)
  ```
- **Out of scope:** glow shader polish (Phase 3)

### P1-05 · HeatmapText component
- **References:** `@docs/PRD.md#§7.2`
- **Files to create:** `cortex/web/app/components/HeatmapText.tsx`
- **Verification:**
  ```bash
  cd cortex/web && npm run typecheck
  # Manual: hero text renders with visible color variation; cold sentences clearly distinguishable
  ```

### P1-06 · Backend Gemma suggestions + `/apply-suggestion`
- **References:** `@docs/PRD.md#§6.1,§8.2,§11`
- **Files to create:** `cortex/gx10/brain/gemma.py`, `cortex/gx10/brain/prompts.py`
- **Files to modify:** `cortex/gx10/brain/main.py`
- **Verification:**
  ```bash
  curl -X POST http://<gx10-ip>:8080/apply-suggestion \
    -d '{"clip_id":"<id>","suggestion_id":"<id>","action":"apply"}' \
    | jq .
  # Must return new text + new job_id within 8s
  ```

### P1-07 · SuggestionPanel + apply loop
- **References:** `@docs/PRD.md#§6.1,§7`
- **Files to create:** `cortex/web/app/components/SuggestionPanel.tsx`
- **Verification:**
  ```bash
  cd cortex/web && npm run typecheck
  # Manual: click cold sentence → suggestion appears → apply → re-render shows warmed sentence
  # Total iteration time: <15s
  ```

> 🛑 **PHASE 1 GATE:** demo Beat 1 (text mode) works 3× in a row. **`/clear` Claude Code session before starting Phase 2.**

---

## Phase 2 — Hours 6–14 — Video Mode + Engagement Prediction

> **Goal:** drop video → 3-track timeline + cold zones visible → brain syncs to playback → engagement card renders predicted rate + percentile.
> **Gate:** demo Beats 2+3 run cleanly 2× in a row.

### P2-01 · Backend `/analyze/video` endpoint
- **References:** `@.claude/skills/tribe-inference/SKILL.md` (REQUIRED), `@docs/PRD.md#§6.3,§8.1`
- **Files to modify:** `cortex/gx10/brain/tribe.py`, `main.py`
- **Verification:**
  ```bash
  curl -X POST http://<gx10-ip>:8080/analyze/video \
    -F "file=@cortex/gx10/cache/hero_video/khan.mp4"
  # Hero clip: returns in <500ms (cache). Novel clip: <45s.
  ```

### P2-02 · Frontend VideoSurface UI
- **References:** `@docs/PRD.md#§6.3,§7`
- **Files to create:** `cortex/web/app/components/VideoSurface.tsx`
- **Verification:** `npm run typecheck` passes; manually: drop video, plays, timeline visible

### P2-03 · EngagementTimeline component (3 tracks)
- **References:** `@docs/PRD.md#§7.3`
- **Files to create:** `cortex/web/app/components/EngagementTimeline.tsx`
- **Verification:** hero video shows 3 visible tracks with cold-zone red highlights

### P2-04 · Brain-sync-with-playback
- **References:** `@.claude/skills/niivue-rendering/SKILL.md`, `@docs/PRD.md#§6.3,§7.1,§10`
- **Files to modify:** `cortex/web/app/components/BrainMonitor.tsx`, `VideoSurface.tsx`
- **Verification:** play hero video → brain pulses in sync. Scrub to 0:18 → brain shows that second's activation.

### P2-05 · Backend pooling + predictor service
- **References:** `@docs/PRD.md#§8.3,§8.4,§11`, `@.claude/skills/engagement-prediction/SKILL.md` (load FIRST), `@.claude/skills/tribe-inference/SKILL.md`
- **Files to create:** `cortex/gx10/brain/pooling.py`, `cortex/gx10/brain/predictor.py`, `cortex/gx10/brain/corpus.py`, `cortex/gx10/tests/test_pooling.py`
- **Files to modify:** `cortex/gx10/brain/main.py` (load predictor at lifespan startup; expose `predictor_loaded` + `corpus_size` in `/health`), `cortex/gx10/brain/models.py` (Pydantic DTOs for predict request/response).
- **Action:**
  1. `pooling.pool_tribe_output(preds: np.ndarray) -> np.ndarray[~25]` — 3 ROI groups × 6 stats + 3 globals. Pure function. Same code as PH-I uses.
  2. `EngagementPredictor.load(pkl_path)` → reads ridge model. `predict(features, followers, duration_s) -> {predicted_rate, percentile, ...}`. Class is intentionally swappable behind this interface (see PRD §11.2 TODO).
  3. `corpus.percentile_rank(rate)` reads `corpus.jsonl` once at startup.
- **Verification:**
  ```bash
  cd cortex/gx10 && CORTEX_STUB_TRIBE=1 CORTEX_STUB_GEMMA=1 pytest tests/test_pooling.py -v
  curl -s http://<gx10-ip>:8080/health | jq '.predictor_loaded, .corpus_size'
  # predictor_loaded must be true, corpus_size must equal `wc -l corpus.jsonl`
  ```
- **Out of scope:** the HTTP endpoint that calls the predictor (P2-06); the upgraded model class (post-baseline)

### P2-06 · `POST /predict-engagement` endpoint
- **References:** `@docs/PRD.md#§9 (endpoint), §11.1`
- **Files to modify:** `cortex/gx10/brain/main.py`
- **Action:** new endpoint takes `{job_id, followers}`. Looks up the analyzed video's pooled features (cached from the `/stream` run). Calls `predictor.predict(...)` + `corpus.percentile_rank(...)`. Returns the JSON shape from PRD §9. Sub-100ms.
- **Verification:**
  ```bash
  JOB=$(curl -s -X POST http://<gx10-ip>:8080/analyze/video -F file=@cortex/gx10/cache/hero_video/khan.mp4 | jq -r .job_id)
  # wait for /stream/$JOB to complete...
  curl -s -X POST http://<gx10-ip>:8080/predict-engagement \
    -H 'content-type: application/json' \
    -d "{\"job_id\":\"$JOB\",\"followers\":10000}" | jq .
  # 200 with predicted_rate ∈ (0,1] and percentile ∈ [0,100]
  ```

### P2-07 · Frontend EngagementCard + wiring
- **References:** `@docs/PRD.md#§7.4, §11.1`
- **Files to create:** `cortex/web/src/app/components/EngagementCard.tsx`
- **Files to modify:** `cortex/web/src/app/components/VideoSurface.tsx` (mount card after `complete`), `cortex/web/src/app/lib/brainClient.ts` (add `predictEngagement(jobId, followers)`)
- **Verification:**
  ```bash
  cd cortex/web && npm run typecheck
  # Manual: drop hero video → after stream completes, card renders with a number + percentile
  # Edit followers field → percentile re-renders client-side without re-running TRIBE
  ```
- **Out of scope:** Cloudinary upload polish; the card's mini-sparkline (Phase 3 polish)

### P2-08 · End-to-end smoke test
- **Files to create:** `cortex/gx10/tests/test_video_e2e.py` (extend existing) + ensure `test_predict_engagement_returns_sane_payload` exists
- **Verification:**
  ```bash
  cd cortex/gx10 && pytest tests/test_video_e2e.py -v
  # Drop hero video → analyze → predict-engagement → all return 200, predicted_rate is finite, percentile in [0,100].
  ```

### P2-09 · Backend originality library — `library.py` + transcript stack (PRD §11.6)
- **References:** `@docs/PRD.md#§11.6,§8.5,§8.6`
- **Files to create:** `cortex/gx10/brain/library.py`, `cortex/gx10/brain/transcribe.py`, `cortex/gx10/brain/text_embed.py`, `cortex/gx10/tests/test_library.py`
- **Action:**
  1. `transcribe.py`: lazy-load `whisper.load_model("base")`, `transcribe(audio_path) -> str`.
  2. `text_embed.py`: lazy-load `SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)`, `embed_text(s) -> np.ndarray[768]` (L2-normed).
  3. `library.py`: `LibraryEntry` dataclass; `load_creator_library(creator_id)` reads `cache/library/<creator_id>/*.json`; `save_entry(entry)` writes one file; `rank_similar(brain_vec, text_vec, library, top_k=3)` returns list with weighted cosine + ROI breakdown via `pooling.ROI_GROUPS`.
- **Verification:**
  ```bash
  cd cortex/gx10 && pytest tests/test_library.py -v
  # rank_similar with mocked brain/text vecs returns top_k matches; cold-start <5 returns empty list.
  ```

### P2-10 · Backend `POST /library/upload` + `GET /library/{creator_id}` + `POST /similarity`
- **References:** `@docs/PRD.md#§9,§11.6`
- **Files to modify:** `cortex/gx10/brain/main.py`, `cortex/gx10/brain/models.py` (already has DTOs)
- **Action:**
  1. `/library/upload` (multipart): re-uses video TRIBE pipeline, also calls `transcribe` + `text_embed`, writes `cache/library/<creator_id>/<video_id>.json`, updates in-memory `_LIBRARIES: dict[str, list[LibraryEntry]]`.
  2. `/library/{creator_id}` returns metadata-only listing.
  3. `/similarity`: pulls cached `pooled_features` + `text_embedding` from `_JOBS[job_id]` (cache them in `/stream` next to engagement features), calls `library.rank_similar`, returns `SimilarityResponse`. Cold-start gate at `SIMILARITY_MIN_LIBRARY_SIZE`.
- **Verification:**
  ```bash
  cd cortex/gx10 && pytest tests/test_video_e2e.py::test_similarity_cold_start -v
  cd cortex/gx10 && pytest tests/test_video_e2e.py::test_similarity_after_5_uploads -v
  ```

### P2-11 · Frontend `LibraryUploader.tsx` + `SimilarityPanel.tsx`
- **References:** `@docs/PRD.md#§7.5,§7.6`
- **Files to create:** `cortex/web/src/app/components/LibraryUploader.tsx`, `cortex/web/src/app/components/SimilarityPanel.tsx`
- **Files to modify:** `cortex/web/src/app/components/VideoSurface.tsx` (mount `SimilarityPanel` below `EngagementCard`), `cortex/web/src/app/lib/brainClient.ts` (add `uploadLibraryEntry`, `getLibrary`, `predictSimilarity`)
- **Verification:** drop 5+ library mp4s in uploader → POST /similarity for a fresh draft → 3 thumbnail cards render in <100ms after EngagementCard. Click → side drawer with match details. Library size <5 → panel hidden, replaced with "upload N more clips" hint.

> 🛑 **PHASE 2 GATE:** Beats 2+3+3.5 work 2× in a row. **`/clear` before Phase 3.**

---

## Phase 3 — Hours 12–18 — Audio Mode + Polish (SCOPE FREEZE AT END)

### P3-01 · Backend `/analyze/audio`
- **References:** `@.claude/skills/tribe-inference/SKILL.md`, `@docs/PRD.md#§6.2,§8.1`
- **Verification:**
  ```bash
  curl -X POST http://<gx10-ip>:8080/analyze/audio -F "file=@cortex/gx10/cache/hero_audio/khan.mp3"
  # Hero clip: <500ms. Novel: <18s.
  ```

### P3-02 · Frontend AudioSurface UI
- **References:** `@docs/PRD.md#§6.2,§7`
- **Files to create:** `cortex/web/app/components/AudioSurface.tsx`
- **Verification:** drop hero audio → 2-track timeline visible → brain pulses (auditory + language only, no visual)

### P3-03 · Tab toggle animation polish
- **References:** `@docs/PRD.md#§7`
- **Files to modify:** `ModeTabs.tsx`, `BrainMonitor.tsx`
- **Verification:** manual — switching tabs feels intentional, not jumpy

### P3-04 · BrainMonitor visual polish (the visible delta)
- **References:** `@.claude/skills/niivue-rendering/SKILL.md`, `@docs/PRD.md#§7.1,§10`
- **Files to modify:** `BrainMonitor.tsx`
- **Action:** glow shader on high-activation vertices, soft particle drift, smooth interpolation, idle breathing cycle
- **Verification:** manual — brain looks "alive." Judges from 30 feet should be drawn to it.

### P3-05 · Failure-path UX
- **References:** `@docs/PRD.md#§12,§13,§15`
- **Files to create:** `cortex/web/app/components/StatusChip.tsx`
- **Verification:**
  ```bash
  # Stop backend
  # Frontend chip must turn gray within 3s
  # Hero clips still loadable from cache
  ```

### P3-06 · Devpost draft + 1-pager
- **Files to create:** `cortex/docs/devpost_draft.md`, `cortex/docs/architecture_1pager.pdf`
- **Verification:** teammate not on the project can read 1-pager and explain it in 60s

### P3-07 · OPTIONAL: ElevenLabs MLH stretch
- **Only if P3-01 through P3-05 are ✅ by hour 16**
- **Files to create:** `cortex/web/app/lib/tts.ts`

### P3-08 · OPTIONAL: upgrade engagement predictor
- **Only if P2-05/06/07 are ✅ and held-out R² of the v0 ridge feels weak (<0.05)**
- **Files to modify:** `cortex/gx10/brain/predictor.py`, `cortex/gx10/scripts/fit_predictor.py`
- **References:** `@docs/PRD.md#§11.2` (TODO list of swappable model classes)
- **Action:** swap `Ridge` for `GradientBoostingRegressor` (zero new deps) or `XGBRegressor` (heavier-sounding, +1 dep). Re-fit. Re-save pickle. The `/predict-engagement` endpoint should not need changes — the swap is behind the `EngagementPredictor` interface.
- **Verification:** `python scripts/fit_predictor.py` → new `R²` printed; smoke tests still pass.

### P3-09 · OPTIONAL: scraper-agent demo stub
- **Only if hours 14–16 free**
- **References:** `@docs/PRD.md#§11.4`, `@.claude/skills/engagement-prediction/SKILL.md`
- **Files to create:** `cortex/gx10/scripts/refit_predictor.py`, screenshot/video of the NemoClaw agent navigating to YouTube Shorts trending and harvesting URLs (does not need to actually run during the demo — superseded by Phase R for the real implementation)
- **Action:** wire the cron-style entrypoint that runs `ingest_shorts.py` against a fresh URL list, then `fit_predictor.py`. Record a 30s loom of the agent path for the Devpost video.
- **Verification:** running `python scripts/refit_predictor.py path/to/urls.txt` end-to-end appends new rows + writes a new pickle.

> 🛑 **PHASE 3 GATE — SCOPE FREEZE.** From hour 18: bug fixes only.

---

## Phase R — NemoClaw curator + inspiration feed (parallel track)

These extend `P3-09 scraper-agent stub` into a real **NemoClaw active-learning curator** (PRD §11.7) and the **trending inspiration feed** (PRD §11.8) — the third demo pillar (*"what should I make next?"*).

**Architecture:** one agent, one loop, two iteration types rotating 5:1 (corpus active-learning : trending pool). No `seed_urls.txt` — query discovery is bootstrap → gap-driven Gemma queries → self-supervised expansion (PRD §11.7 "How the agent knows what to scrape").

**Scope rules:**
- Phase R does **not** gate the demo path. The curator runs only when `cache/curator.enabled` exists; it's off by default for Phase 0–3.
- Strict dependency order: R-01 → R-02 → R-03 (corpus iteration end-to-end) → R-04 (trending iteration mode added to the same loop) → R-05 (endpoint) → R-06 (UI).
- If running into the Phase 3 scope freeze without R-XX done, downgrade that step to "demo-able stub" — one successful end-to-end iteration recorded as a 30s loom.
- The /inspiration UI lives on `/library` (where the centroid is computed). Do **not** add it to `/predict`.

### R-01 · Backend `curator.py` skeleton + uvicorn lifespan ✅
- **References:** `@docs/PRD.md#§11.7`
- **Files to create:** `cortex/gx10/brain/curator.py` ✅
- **Files to modify:** `cortex/gx10/brain/main.py` (lifespan spawn/cancel + `_active_streams` counter + `try/finally` around `/stream/{job_id}` + `GET /curator/status`) ✅
- **Action:** asyncio coroutine — priority gate (sleep if `_active_streams > 0`), iteration-type rotation (`type = "trending" if iter_count % 6 == 5 else "corpus"`), no-op iteration body for now, opt-in master gate (`cache/curator.enabled`) + kill-switch precedence (`cache/curator.disabled` wins), `GET /curator/status` endpoint.
- **Verification:** `pytest tests/test_curator.py -v` → 8/8 pass (rotation, gate-file precedence, priority gate, lifespan cancellation, status-endpoint shape). Full suite: 54/54 pass. Manual on GX10 (deferred): `bash scripts/01_start_brain.sh` → `curl /curator/status` returns `{running: true, ...}` only after `touch cache/curator.enabled`.
- **Notes for R-02/R-03:** `_active_streams` is a module-level int incremented in the `/stream/{job_id}` generator's `try/finally`. Iteration body in `_run_iteration` is a logging no-op — R-02 wires query selection, R-03 wires scrape+refit. When R-03 calls TRIBE/Whisper, route through `asyncio.to_thread(...)` to avoid stalling live `/analyze/video`.

### R-02 · Query selection — bootstrap + gap-finder + Gemma + self-expansion ✅
- **References:** `@docs/PRD.md#§11.7` "How the agent knows what to scrape", `@.claude/skills/engagement-prediction/SKILL.md`
- **Files to create:** `cortex/gx10/brain/curator_gap.py` ✅ (with `BOOTSTRAP_QUERIES` + `TRENDING_QUERIES` constants); `cortex/gx10/cache/curator_query_pool.jsonl` (auto-created at runtime by R-03)
- **Files to modify:** `cortex/gx10/brain/gemma.py` (added `GemmaService.generate(prompt, max_new_tokens)` with `CORTEX_STUB_GEMMA=1` deterministic stub) ✅; `cortex/gx10/brain/predictor.py` (added `r2: float | None` field, default None means cold-start) ✅; `cortex/gx10/brain/config.py` (8 curator constants: cold-start thresholds, query counts per iteration, pool sample rate, query pool path) ✅
- **Action:** `pick_queries(iter_type, corpus, predictor, gemma, query_pool_path, rng)` — three-source priority logic:
  1. cold start (R² < 0.05 OR corpus < 100) → sample from `BOOTSTRAP_QUERIES` (3/iter)
  2. warm predictor → density-only `find_gap` → Gemma prompt → 5 queries (R-03 will swap density-only for residual-variance)
  3. ~10% of iterations → augment with one query from `curator_query_pool.jsonl`
  Trending iterations always use `TRENDING_QUERIES` (1/iter).
- **Verification:** `pytest tests/test_curator_gap.py -v` → 16/16 pass (constants, cold-start gate × 5, gap-finder × 3, gemma_translate stub + fallback, pick_queries × 5). Full suite: 70/70 pass.
- **Notes for R-03:** density-only gap-finder is a placeholder — TODO marker at `curator_gap.find_gap` to swap for per-bin residual-variance once `predictor.predict()` runs against the corpus held-out set. R-03 also needs to *write* to `curator_query_pool.jsonl` (Gemma summarizes top-quartile transcripts → append). When calling `gemma.generate()` from the curator coroutine, route through `asyncio.to_thread()` to avoid stalling the event loop.

### R-03 · URL discovery + scraper + feature extractor + refit + rollback (corpus iteration) ✅
- **References:** `@docs/PRD.md#§11.7` steps 3-6
- **Files to modify:** `cortex/gx10/brain/curator.py` (corpus iteration end-to-end ~430 lines added) ✅; `cortex/gx10/scripts/fit_predictor.py` (extracted importable `fit_predictor()` function + CLI wrapper, filters `excluded:true` rows) ✅; `cortex/gx10/brain/tribe.py` (added `asyncio.Lock` for shared TRIBE access) ✅; `cortex/gx10/brain/main.py` (`/stream/{job_id}` + `/library/upload` acquire the TRIBE lock) ✅; `cortex/gx10/brain/predictor.py` (round-trip `r2` field through save/load bundle) ✅; `cortex/gx10/brain/config.py` (8 new R-03 constants) ✅
- **Action:** for each query → `yt-dlp ytsearch20:<query>` (async subprocess) metadata-only → filter (≤ `MAX_CLIP_DURATION_S`, views > `CURATOR_MIN_VIEWS`, dedupe vs `read_existing_video_ids`) → cap at `CURATOR_URLS_PER_ITERATION` → per-URL: re-check active_streams → download mp4 to tempdir → acquire `tribe_service.lock` → `to_thread(analyze_video)` → pool features → `build_corpus_row` → `append_corpus_row` → unlink mp4 in finally. After all rows added: snapshot pickle to `.snapshot` → in-process `fit_predictor` (in `to_thread`) → reload predictor singleton → if `r2_before - r2_after > CURATOR_R2_REGRESSION_THRESHOLD`, restore snapshot + mark rows `excluded:true,excluded_reason:"r2_regression"` in corpus.jsonl. Append iteration row to `curator_log.jsonl`. On successful iteration with top-quartile rows, Gemma summarizes title+uploader → 1-2 candidate queries → append to `curator_query_pool.jsonl` with FIFO cap.
- **Verification:** `pytest tests/test_curator.py -v` → 18/18 pass (9 new R-03 tests: end-to-end corpus iteration with stubbed yt-dlp+TRIBE, active-stream mid-iteration yield, dedupe across iterations, filter applies all three rules, `_exclude_rows_in_corpus` markers, FIFO pool truncation, query expansion gates + happy path, `fit_predictor` skips excluded rows). Full suite: 84/84 pass. Manual on GX10 (deferred): start with 50-row seed corpus → 3 corpus iterations → ≥ +30 rows, log has 3 entries with R² before/after, no mp4 leftover in `cache/`.
- **Notes for R-04:** trending iteration's pipeline is identical (yt-dlp + TRIBE + Whisper + nomic) but writes to `cache/trending/<yyyy-mm-dd>/<id>.json` instead of `corpus.jsonl`. The trending branch in `_run_iteration` currently logs "deferred to R-04" — replace with a real `_run_trending_iteration` that reuses `_ytsearch_metadata` + `_filter_search_results` + `_ytdlp_download` + the TRIBE lock, then routes to a `LibraryEntry`-shaped JSON write. Query selection already supports trending mode via `pick_queries(iter_type="trending")`.

### R-04 · Trending iteration mode (same loop, different terminal step) ✅
- **References:** `@docs/PRD.md#§11.8`
- **Files to modify:** `cortex/gx10/brain/curator.py` (added `_run_trending_iteration` + 6 helpers ~190 lines; replaces R-03 trending no-op) ✅; `cortex/gx10/brain/main.py` (`/curator/status` now calls `count_trending_entries()` + reports `predictor.r2`) ✅; `cortex/gx10/brain/config.py` (3 R-04 constants: `CURATOR_TRENDING_DIR`, `CURATOR_TRENDING_TTL_DAYS`, `CURATOR_TRENDING_URLS_PER_ITERATION`) ✅
- **Action:** trending iteration reuses R-03's `_ytsearch_metadata` + `_filter_search_results` + `_ytdlp_download` + the TRIBE lock. Per-URL pipeline: download → `async with tribe_service.lock` + `to_thread(analyze_video)` → pool + ROI means → `to_thread(transcribe)` (Whisper) → `to_thread(embed_text)` (nomic-embed) → emit `LibraryEntry`-shape dict + trending extras (`source_url`, `creator_handle`, `view_count`, `engagement_rate`) → write to `cache/trending/<yyyy-mm-dd>/<video_id>.json`. Cleanup runs *inline at the start* of each trending iteration (`_prune_old_trending_dirs`) — no separate cron. Dedupe spans the entire trending pool across all date partitions (`_read_trending_video_ids`). Status endpoint reports `trending_pool_size = count_trending_entries()`.
- **Verification:** `pytest tests/test_curator.py -v` → 24/24 pass (6 new R-04 tests: end-to-end trending iteration produces date-partitioned entries with all 12 keys, active-stream yield, cross-date dedupe, prune deletes only expired + skips malformed dir names, `count_trending_entries` walks all partitions, `_compute_engagement_rate` handles zero views). Full suite: 90/90 pass. Manual on GX10 (deferred): force `iter_count % 6 == 5` → trending iteration runs against real yt-dlp + TRIBE + Whisper + nomic-embed → ≥ 3 JSONs at `cache/trending/<today>/*.json`, each with `tribe_pooled`, `text_embedding`, `roi_means`, plus trending fields. Old fake `cache/trending/2025-01-01/` → next iteration prunes it.
- **Notes for R-05:** trending entries are written as plain JSON dicts (not `LibraryEntry` instances) but the schema is a strict superset — `LibraryEntry.from_json()` works on them for the centroid math. R-05's `compute_centroid()` reads `tribe_pooled` + `text_embedding`; both are present. Response-shape fields (`source_url`, `creator_handle`, etc.) are passed through unchanged.

### R-05 · Backend `GET /inspiration/{creator_id}` endpoint
- **References:** `@docs/PRD.md#§11.8`
- **Files to modify:** `cortex/gx10/brain/main.py`, `cortex/gx10/brain/library.py` (add `compute_centroid`, `rank_against_pool`)
- **Action:** load creator library → compute L2-normed centroid (brain + text) → cosine-fuse against all entries in `cache/trending/<all-dates>/` → top-3 with thumbnail + source URL + ROI breakdown. Cold-start (library < 5) → message + empty list.
- **Verification:** unit tests in `tests/test_inspiration.py` — library ≥ 5 + trending pool ≥ 50 → 3 recommendations with score 0.4–0.9 range. Library = 0 → cold-start message. Trending pool empty → message indicating curator hasn't harvested yet.

### R-06 · Frontend `InspirationFeed.tsx` on /library
- **References:** `@docs/PRD.md#§11.8`
- **Files to create:** `cortex/web/src/app/components/InspirationFeed.tsx`
- **Files to modify:** `cortex/web/src/app/library/page.tsx` (mount feed below the clips table), `cortex/web/src/app/lib/brainClient.ts` (add `getInspiration`), `cortex/web/src/app/lib/types.ts` (add `InspirationResponse`)
- **Action:** 3 cards horizontally — thumbnail + dominant-ROI chip + score + outbound link (target=_blank). Hidden during cold-start. `onError` thumbnail fallback for deleted source videos.
- **Verification:** `npm run typecheck && npm run build` clean. With stub backend returning 3 recs, `/library` shows the section with 3 cards. Library = 0 → section hidden.

---

## Phase 4 — Hours 18–28 — Demo Production

- [ ] **P4-01 · Record 60s demo video** — full booth, all 6 beats, edit to <60s
- [ ] **P4-02 · Rehearse 90s pitch** — `@docs/PRD.md#§14` verbatim, personalize, 5x
- [ ] **P4-03 · Devpost final** — title, tagline, description, video, GitHub link, all tracks tagged: Flicker to Flow, ASUS, Cloudinary, Best UI/UX, MLH Best Use of Gemma. Stretch: Cognition.
- [ ] **P4-04 · Print 1-pager handout** — physical paper for judge table

---

## Phase 5 — Hours 28–36 — Buffer

- [ ] **P5-01 · Stranger dry-run** — non-team person tries all 3 modes, fix confusion
- [ ] **P5-02 · Backup laptop configured identically** — same code, same Tailscale, same `.env.local`, tested
- [ ] **P5-03 · Final rehearsal — 5 runs** — actual hardware, time each, target 2.5min
- [ ] **P5-04 · Stop coding at hour 34** — sleep > debugging

---

## Emergency Pivots

| If this breaks at hour N... | Pivot to... | Tasks to redo |
|---|---|---|
| TRIBE env still broken at Wed EOD | Abandon Cortex → 3D Movement Coach | All |
| Niivue shader broken at hour 14 | Rotating PNG video instead of live BrainMonitor | P3-04 → swap |
| Gemma weak at hour 16 | Hardcoded suggestion library by cold-zone region | P1-06 → hardcode |
| `corpus.jsonl` < 30 rows by hour 14 | Skip percentile rank; show only predicted rate; mention "trained on N=20 — pipeline scales, seed set is small" | PH-I → ship what we have |
| Predictor R² ≤ 0 by hour 16 | Drop to 3-bucket classifier (top-quartile / median / bottom-quartile via thresholds on `n_cold_zones` + `language.fraction_below_zero`) | P2-05 → simplify |
| Tailscale blocked at venue | Phone hotspot for laptop↔GX10 | P0-C |
| GX10 dies mid-demo | Backup laptop running cortexlab Streamlit dashboard | P5-02 |

---

*Task log lives here. When verification passes, mark ✅ and commit. Spawned follow-ups get added inline with parent ref like "(from P2-04)".*
