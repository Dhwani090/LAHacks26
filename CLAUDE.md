# CLAUDE.md — Cortex Project Rules

> Auto-loaded every Claude Code session. Keep this file short — bloat causes important rules to get lost.
> For domain-specific knowledge (TRIBE, Niivue), see `.claude/skills/`.
> If you're Claude Code: read this file fully, then ask which task in `@docs/TASKS.md` we're working on. **Do not start coding until I confirm.**

---

## 1. What we're building

A Next.js + niivue web app that talks to a FastAPI server on an ASUS GX10 (128GB unified memory). The backend runs **TRIBE v2** (Meta FAIR neuroscience model, released March 2026) plus **Gemma 2B**. Three modes — text, audio, short-form video — share one engine. Tells creators what an average viewer's brain did with their content. **36-hour hackathon, demo Sunday morning, LA Hacks 2026.**

Full spec: `@docs/PRD.md`. Work queue: `@docs/TASKS.md`. Domain skills: `@.claude/skills/`.

## 2. Hard non-goals — refuse if asked

- iOS or Android app
- User accounts, login, auth, OAuth
- Multi-day project history or shareable links
- Long-form content (>60s video, >60s audio, >500 words text)
- Auto-editing of video by cutting low-engagement spans — removed; the diagnostic is the product. (Auto-regeneration of new content — B-roll, voice synthesis, music swap — also out.)
- Real-time live camera or microphone input
- Cloud inference fallback if GX10 is down — local or nothing
- ChromaDB, vector stores, anything beyond filesystem JSON cache
- Phone-side ZETIC integration — explicitly skipped, do NOT bolt on
- Anything discovered after hour 18 (scope freeze)

If a teammate asks for any of these, point at this section and stop.

## 3. Tech stack — locked

**Frontend** (`cortex/web/`): Next.js 14 App Router, TypeScript, Tailwind, `@niivue/niivue` + `niivue-react`, `framer-motion`, `@cloudinary/react`. Native `fetch` + `EventSource`. NO axios, tRPC, Apollo, Redux.

**Backend** (`cortex/gx10/`): Python 3.11, FastAPI + `sse-starlette`, `tribev2` from GitHub, `cortexlab-toolkit`, `transformers` + Gemma 2B, `scikit-learn` (engagement predictor — ridge baseline, model class is swappable per PRD §11.2), `yt-dlp` (corpus ingest), Pydantic v2. In-memory dict + filesystem JSON cache + `corpus.jsonl`. NO Chroma, NO SQLite, NO vector DB.

**Transport**: HTTP/JSON + SSE over Tailscale. NO WebSockets, NO gRPC.

If a library isn't above, ask before adding it.

## 4. Conventions

- **File header.** Every source file starts with a 5-line comment naming the `PRD.md` section it implements.
- **No TODOs committed.** Implement it or don't create the file.
- **No silent failures.** Log at `console.error` (frontend) or `logger.error` (backend) with the exact error.
- **Magic numbers in one file.** Frontend: `app/lib/tuning.ts`. Backend: `gx10/brain/config.py`.
- **Imports.** No wildcards.
- **Commits.** Present-tense subject ≤60 chars. PRD section in body if applicable: `brain: add /analyze/text endpoint (PRD §9)`.

## 5. Commands

```bash
# Frontend (laptop, from cortex/web/)
npm install                              # first time
npm run dev                              # dev on :3000
npm run typecheck                        # ALWAYS run after edits
npm run build                            # verify prod build before commit

# Backend (GX10 via SSH, from cortex/gx10/)
bash scripts/00_tailscale_up.sh
bash scripts/01_start_brain.sh           # loads TRIBE + Gemma, uvicorn :8080
bash scripts/99_healthcheck.sh           # verify endpoints
pytest tests/test_smoke.py -v            # ALWAYS run after backend edits

# Find GX10 IP
tailscale ip -4                          # on the GX10
```

Required env (`cortex/web/.env.local`):
```
NEXT_PUBLIC_BRAIN_BASE_URL=http://<gx10-tailnet-ip>:8080
NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME=<from cloudinary dashboard>
NEXT_PUBLIC_CLOUDINARY_UPLOAD_PRESET=<unsigned preset>
```

Required env (GX10 `~/.bashrc`):
```
export HF_TOKEN=<from huggingface.co/settings/tokens>
export HF_HUB_DOWNLOAD_TIMEOUT=300
```

## 6. The four-phase workflow — follow EVERY non-trivial task

Per Anthropic's official Claude Code guide.

### Phase 1: Explore
Before writing code, read the relevant files. Use `@` references — `@app/components/BrainMonitor.tsx`, `@gx10/brain/tribe.py`, `@docs/PRD.md#§7.1`. If unfamiliar with a domain, **load the relevant skill** from `@.claude/skills/`. If the codebase area is large, **use a subagent** to investigate so the exploration doesn't fill main context.

### Phase 2: Plan
Output a plan in this exact format and **wait for human approval**:

```
## Plan for: <task name>
**PRD section(s) consulted:** <§N.N list>
**Skill(s) loaded:** <if any>
**Files to create:** <paths>
**Files to modify:** <paths>
**Public interfaces (signatures only):** <function/component signatures>
**Verification command:** <exact bash one-liner that proves it works>
**Out of scope (will NOT touch):** <files/features I won't change>
**Risks / questions:** <anything ambiguous>
```

### Phase 3: Implement
Write code. ONE task per session. Do not refactor neighboring code. Do not add "while we're here" improvements.

### Phase 4: Verify
Run the verification command. If it fails, fix the code — do not silence the test. **Never mark a task done without running verification.** If verification needs the GX10 or hardware, tell the human to run it and wait.

When done, output:
```
## Task complete: <task name>
**Files changed:** <paths>
**Verification command run:** <command>
**Verification status:** <pass/fail/needs-human-verification>
**Next task per TASKS.md:** <task id>
**Notes for next session:** <anything the next Claude Code session should know>
```

## 7. Context discipline (CRITICAL on a 30-hour clock)

- **`/clear` between unrelated tasks.** A polluted context produces worse code than a fresh session.
- **After 2 failed corrections on the same issue, `/clear` and start a fresh session** with a more specific prompt.
- **Use subagents for investigation** so research doesn't fill your main context: *"use a subagent to investigate how X works."*
- **Use `@` to reference files** — Claude reads them on-demand. Don't paste large files inline.
- **Don't ask me to paste the whole PRD.** `@docs/TASKS.md` lists which `@docs/PRD.md#§N` to load per task.

## 8. Skills (load on demand, NOT auto-loaded)

Domain-specific patterns live here. Claude Code loads them only when invoked or when the task description matches their description.

- `@.claude/skills/tribe-inference/SKILL.md` — calling `TribeModel`, gotchas, output shapes
- `@.claude/skills/niivue-rendering/SKILL.md` — `niivue-react` patterns, mesh loading, vertex colors
- `@.claude/skills/engagement-prediction/SKILL.md` — yt-dlp ingest, TRIBE feature pooling, ridge regression baseline, scraper-agent roadmap

If a task touches one of these domains, load the skill first.

## 9. Common failure patterns to avoid

From Anthropic's official best-practices guide. Seen them all in real Claude Code sessions:

- **The kitchen-sink session.** Mixing unrelated tasks. **Fix:** `/clear` between tasks.
- **Correcting over and over.** Context fills with failed attempts. **Fix:** after 2 failed corrections, `/clear` and re-prompt with what you learned.
- **The trust-then-verify gap.** Plausible-looking code that doesn't actually work. **Fix:** every task has a verification command. Run it.
- **The infinite exploration.** Reading hundreds of files to "understand" the codebase. **Fix:** use a subagent or scope to specific `@file` references.
- **Over-specified instructions.** Important rules get lost in noise. **Fix:** if Claude already does X correctly without being told, don't tell it.

## 10. Hard rules — non-negotiable

- **Never invent libraries.** If not in §3, ask first.
- **Never invent TRIBE v2 API shapes.** TRIBE was released March 2026 — your training data predates it. Read `@.claude/skills/tribe-inference/SKILL.md` and https://github.com/facebookresearch/tribev2 before calling `TribeModel`. Do NOT guess.
- **Never invent Niivue API shapes.** Niche WebGL library, shallow training coverage. Read `@.claude/skills/niivue-rendering/SKILL.md` and https://niivue.com/docs/ before using `Niivue` or `NiiVueCanvas`.
- **Never silence a failing test.** Tell me. We fix it.
- **Never modify files outside the task scope.** If you spot a bug elsewhere, log it as a comment and move on.
- **YOU MUST verify every task before marking complete.** If you can't verify it, don't ship it.

---

*Last updated: pre-hackathon. Loaded automatically every session. See `@docs/PRD.md` for spec, `@docs/TASKS.md` for work queue, `@.claude/skills/` for domain knowledge.*
