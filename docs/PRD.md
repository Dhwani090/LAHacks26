# PRD.md — Cortex

> **The product:** an editing room for any short-form content where a foundation neuroscience model on the GX10 predicts what the average viewer's brain did with your work. Three input modes — text, audio, short-form video — sharing one engine and one brain visualization.
>
> **The pitch in one breath:** *"Every creator ships work without knowing if it landed. Cortex tells you — by predicting how the average brain responded."*
>
> **Demo day:** LA Hacks 2026, Sunday morning, UCLA Pauley Pavilion. **36-hour build, 4-person team.**
>
> **Track:** Flicker to Flow (Productivity).
> **Sponsor stack:** ASUS Ascent GX10 + Cloudinary + MLH Best Use of Gemma + Best UI/UX. Stretch: Cognition.

---

## §0 — Success criteria (measurable wins)

The project succeeds if and only if all of these are true on Sunday morning:

1. **Demo runs end-to-end in <3 minutes** with all three modes (text, audio, video) demonstrated
2. **Auto-improve loop produces a visible v1→v2 improvement** on at least 2 hero video clips, repeatable
3. **Judge can drop their own content** in any of the three modes and see a brain visualization within 60 seconds (or fall back gracefully to a cached hero clip)
4. **Devpost submission is complete** with video, GitHub link, and all four sponsor/side-prize tracks tagged: Flicker to Flow, ASUS, Cloudinary, MLH Best Use of Gemma, Best UI/UX
5. **The brain visualization is visibly polished** — judges from 30 feet away should be drawn to the booth by the rotating glowing brain

If any of these aren't met by hour 30, focus the remaining time on the gap.

---

## §1 — Vision

Every writer, editor, marketer, podcaster, founder, and short-form creator ships content guessing whether it landed. They wait for analytics two weeks later. Cortex closes the loop. Drop in a script, an audio take, or a 30-second video — Cortex predicts the average viewer's second-by-second neural engagement using **TRIBE v2**, a foundation model Meta FAIR released in March 2026, and renders it as a glowing cortical surface pulsing alongside the content. A small Gemma model reads the engagement curve and suggests specific edits. For video, an auto-improve loop applies cuts and re-runs the prediction, showing v1→v2→v3 with the brain getting healthier each pass.

Why this only works on this hardware: TRIBE v2 needs ~30GB VRAM with all encoders loaded. The GX10's 128GB unified memory holds TRIBE + Gemma + ffmpeg orchestration concurrently, with sub-second response paths for text and ~25s for video re-inference. A laptop cannot hold the model. A cloud API would round-trip the data — defeating the privacy story creators care about for unreleased content.

Why this only works now: TRIBE v2 was open-sourced one month ago. Most teams at LA Hacks 2026 will not have heard of it. Originality is asymmetric.

---

## §2 — Hard non-goals

- iOS or Android app — desktop web only
- User accounts, login, auth, OAuth, social sign-in
- Multi-day project history or shareable links
- Long-form content (>60 seconds video, >60 seconds audio, >500 words text)
- Auto-regeneration of new content (no B-roll generation, no voice synthesis, no music swap, no script rewriting beyond inline suggestions)
- Real-time live camera or microphone input
- Cloud inference fallback if the GX10 is down — local or nothing
- Multi-user collaboration, comments, sharing
- ChromaDB, vector stores, anything beyond filesystem JSON cache
- Phone-side ZETIC integration — explicitly skipped, do not bolt on
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
- **`transformers` + Gemma 2B** for edit suggestions
- **`ffmpeg-python`** for video auto-edit operations
- In-memory cache + filesystem JSON cache. **NO Chroma, NO SQLite.**
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
- ffmpeg invoked as subprocess per auto-improve call
- Total resident: ~35-40GB of 128GB. Plenty of headroom.

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
| PH-H | Pre-render auto-improve V1→V2→V3 sequences for 2 video hero clips. | Same | 2 | For each of 2 clips: 3 MP4s + 3 JSON outputs exist; visual inspection confirms V2 and V3 look better |

Total pre-hack budget: **~12 hours**. If PH-B fails by **Wed April 23 EOD**, pivot to 3D Movement Coach.

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

**Input:** 15-60s audio clip (mp3, wav, m4a).
**TRIBE pathway:** audio + language (Wav2Vec-BERT + LLaMA, no V-JEPA).
**Inference latency:** ~15s.
**Output:** waveform + 2-track timeline (auditory green, language orange), brain pulses (no visual cortex).
**Verification:** drop hero audio → 2-track timeline visible within 18s. Brain shows quieter activation than video mode (auditory + language only).

### 6.3 Video mode (the spectacle + auto-improve)

**Input:** 15-60s video clip (mp4, mov).
**TRIBE pathway:** full trimodal.
**Inference latency:** ~25-40s.
**Output:** video player + 3-track timeline (visual blue, auditory green, language orange), brain syncs to playback.
**Auto-improve:** click button → Gemma reasoning streams → ffmpeg cuts → TRIBE re-runs → V2 loads → repeat for V3.
**Verification:** drop hero clip → 3-track timeline visible within 45s. Click `Auto-improve` → V2 loads in <30s with visibly different engagement curve. Click again → V3 loads.

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
│   ├── VideoSurface.tsx    # Video uploader + player + 3-track timeline + auto-improve
│   ├── EngagementTimeline.tsx  # Reusable N-track timeline
│   ├── HeatmapText.tsx     # Per-word color overlay
│   ├── SuggestionPanel.tsx # Gemma suggestions, click-to-apply
│   ├── AutoImproveButton.tsx  # Streaming reasoning text
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
- Click on cold zone opens SuggestionPanel for that timestamp

### 7.4 AutoImproveButton verification
- On click, timeline area switches to "reasoning mode" with streaming text
- Brain dims to ~30% opacity with thinking animation
- On `complete` event, player swaps to V2 cleanly
- See `@.claude/skills/auto-improve/SKILL.md` for orchestration patterns

---

## §8 — Backend modules (FastAPI on GX10)

```
gx10/
├── brain/
│   ├── main.py              # FastAPI app, all endpoints
│   ├── config.py            # All tuning constants
│   ├── models.py            # Pydantic DTOs
│   ├── tribe.py             # TRIBE inference wrapper
│   ├── gemma.py             # Gemma 2B suggestion service
│   ├── editor.py            # ffmpeg wrapper for auto-improve cuts
│   ├── cache.py             # Filesystem JSON cache + fallback
│   ├── streaming.py         # SSE helpers
│   └── prompts.py           # All Gemma prompts
├── scripts/
│   ├── 00_tailscale_up.sh
│   ├── 01_start_brain.sh
│   ├── 99_healthcheck.sh
│   └── prerender_heroes.py  # Pre-hack PH-E/F/G/H
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
- `suggest_edits(mode="text", cold_zones, transcript)` returns ≥1 valid `EditSuggestion` in <3s
- For text mode: returns rewrite of cold sentence
- For audio/video: returns cut operation with valid timestamps

### 8.3 `editor.py` verification
- Unit test: cut a 30s clip from 14-21s → produce valid 23s mp4 that plays cleanly
- Pure function — no global state
- Sanitizes timestamps (clamps to valid range, rejects overlap)

### 8.4 `cache.py` verification
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

### POST `/auto-improve`
**Request:** `{clip_id: string, version: int}`
**Response:** `{job_id: string}`

### GET `/stream-improve/{job_id}` (SSE)
1. `event: reasoning` — Gemma's chain-of-thought streamed token-by-token
2. `event: cutting` — `{cut: {start, end}}`
3. `event: cut_applied` — `{v2_url: string}`
4. `event: reanalyzing` — `{}`
5. `event: brain_frame` events for v2
6. `event: complete` — `{v2_engagement, v2_cold_zones, v2_suggestions}`

**Verification:** end-to-end auto-improve on hero clip completes in <60s with all 6 event types observed

### GET `/health`
**Response:** `{status, tribe_loaded, gemma_loaded, cache_size, gx10_uptime_s}`
**Verification:** returns 200 with `tribe_loaded: true` and `gemma_loaded: true`

### POST `/apply-suggestion`
**Request:** `{clip_id, suggestion_id, action: "apply"|"reject"}`
**Response:** for text — new text + new analysis job_id. For audio/video — same as auto-improve scoped to one suggestion.

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

## §11 — Auto-improve loop

The money beat. Detailed orchestration spec lives in `@.claude/skills/auto-improve/SKILL.md`. Key flow:

1. User clicks `Auto-improve` on analyzed video
2. Frontend POSTs `/auto-improve`, opens SSE
3. Gemma reads cold zones + transcript → outputs reasoning + structured cut JSON
4. Backend streams Gemma's reasoning as it generates (fills 25s of dead air with visible AI work)
5. ffmpeg applies cut → produces v2.mp4
6. Backend re-runs TRIBE on v2 → streams new brain frames
7. Frontend swaps player to v2 → re-renders timeline → re-pulses brain

**Failure modes** (in skill):
- Gemma returns invalid JSON → retry once, then fall back to heuristic cut
- ffmpeg fails → return v1 unchanged with error event
- TRIBE re-inference fails → use cached v2 for hero clips

**Verification:** end-to-end loop on hero clip in <60s. Verbose mode shows all 6 event types.

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
| R5 | Auto-improve re-inference latency too long for demo | Medium | High | Pre-cache v1→v2→v3 for hero clips (PH-H); narrate the wait with streaming reasoning text |
| R6 | TRIBE output noisy on judge-uploaded clips | Medium | Medium | Tooltip on upload: "best with naturalistic video and conversational text"; pivot to hero clips |
| R7 | GX10 dies mid-demo | Low | Catastrophic | Backup laptop with cortexlab Streamlit dashboard as full fallback |
| R8 | ffmpeg cut produces broken video | Low | Medium | Test with 10 sample clips during PH-H; sanitize timestamps |

---

## §14 — Demo script (verbatim, for rehearsal)

**Beat 1 — open with text (15s).**
Already on Text tab. Pre-loaded paragraph. Click `Diagnose`.
> *"Most creators ship work and wait two weeks for analytics to know if it landed. We don't. Watch."*

5s render. Heatmap underlines. Two sentences orange, middle sentence blue.
> *"Three sentences in. The model says the average reader checked out on the middle one."*

Click cold sentence → Gemma suggestion → Apply → re-render in 5s → warm.
> *"Five-second iteration. Edit, see the brain, edit again."*

**Beat 2 — switch to video (20s).**
Hit Video tab. Pre-rendered 30s hero clip. Hit play. Brain syncs. Around 0:18, language region visibly dims.
> *"Right there. Eighteen seconds. They lost the average viewer."*
Pause.

**Beat 3 — auto-improve (40s, the money beat).**
Click `Auto-improve`. Streaming text in timeline area:
*"identified language drop at 0:14... transcript suggests pacing issue... testing 7-second cut... regenerating brain response..."*

~25s of visible AI work. v2 loads. Brain re-pulses. Cold zone gone.

Click `Auto-improve again`. v3 loads ~25s later. Even healthier.
> *"Three cuts. Ninety seconds. The video improved itself, watching the brain at every step."*

**Beat 4 — switch to audio (15s).**
Hit Audio tab. Pre-rendered podcast clip. Brain pulses but only auditory + language regions.
> *"Same diagnostic, audio only. The model knows when a speaker loses themselves."*

**Beat 5 — hand the tablet over (45s).**
> *"Try one. Email, tweet, voice memo, video — whatever you've got."*

Most judges paste text first. They watch one of their own sentences underline blue. They react.

**Beat 6 — close (15s).**
Step back, gesture at GX10.
> *"Same engine, three surfaces, all on the box behind me. Model came out a month ago — most teams couldn't load it, it needs 30 gigs of GPU memory. We have 128. Whatever you ship, this is the first tool that tells you if it landed before your audience does."*

Slide tablet back. Walk three steps away.

**Total runtime:** ~2.5 minutes.

---

## §15 — Failure-mode pivots

| If this breaks at hour N... | Pivot to... |
|---|---|
| TRIBE env still broken at Wed EOD pre-hack | **Abandon Cortex.** Pivot to 3D Movement Coach. |
| Niivue shader broken at hour 14 | Replace BrainMonitor with rotating PNG video of pre-rendered brain animation |
| Auto-improve loop not working at hour 14 | Drop to manual V1/V2 toggle (pre-cached pair, button labeled `Improved cut`) |
| Gemma suggestions weak at hour 16 | Hand-written suggestion library indexed by cold-zone region |
| Tailscale blocked at venue | Phone hotspot dedicated to laptop↔GX10 |
| GX10 unavailable | Backup laptop running cortexlab Streamlit dashboard |

---

*Last updated: pre-hackathon. See `@docs/CLAUDE.md` for project rules, `@docs/TASKS.md` for work queue, `@.claude/skills/` for domain-specific patterns.*
