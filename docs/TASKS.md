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
- **Out of scope:** the predictor itself (PH-J), live ingest endpoint, OpenClaw agent

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

> 🛑 **PHASE 2 GATE:** Beats 2+3 work 2× in a row. **`/clear` before Phase 3.**

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
- **Files to create:** `cortex/gx10/scripts/refit_predictor.py`, screenshot/video of the OpenClaw or NemoClaw agent navigating to YouTube Shorts trending and harvesting URLs (does not need to actually run during the demo)
- **Action:** wire the cron-style entrypoint that runs `ingest_shorts.py` against a fresh URL list, then `fit_predictor.py`. Record a 30s loom of the agent path for the Devpost video.
- **Verification:** running `python scripts/refit_predictor.py path/to/urls.txt` end-to-end appends new rows + writes a new pickle.

> 🛑 **PHASE 3 GATE — SCOPE FREEZE.** From hour 18: bug fixes only.

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
