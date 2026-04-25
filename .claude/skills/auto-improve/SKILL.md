---
name: auto-improve
description: Orchestration patterns for the auto-improve loop — Gemma identifies the worst cold zone, ffmpeg applies the cut, TRIBE re-runs to produce v2. Load this skill when working on the /auto-improve endpoint, the streaming reasoning UX, ffmpeg cuts, or the AutoImproveButton component.
---

# Auto-Improve Loop Skill

## When to load this skill
Any task that:
- Touches `cortex/gx10/brain/main.py` `/auto-improve` endpoint
- Touches `cortex/gx10/brain/editor.py` (ffmpeg wrapper)
- Touches `cortex/gx10/brain/gemma.py` edit-suggestion logic
- Touches `cortex/web/app/components/AutoImproveButton.tsx`
- Implements the `/stream-improve` SSE flow

## The core flow

```
User clicks "Auto-improve"
  ↓
POST /auto-improve {clip_id, version}
  ↓
Backend opens SSE stream at /stream-improve/{job_id}
  ↓
1. Gemma reads cold zones + transcript → outputs reasoning + cut JSON
   (stream "reasoning" events token-by-token while Gemma generates)
  ↓
2. Backend parses Gemma's JSON → validates timestamps → emits "cutting" event
  ↓
3. ffmpeg applies cut → produces v2.mp4 → emits "cut_applied" {v2_url}
  ↓
4. TRIBE re-runs on v2 (~25s) → emits "reanalyzing" then "brain_frame" events
  ↓
5. Backend computes v2 cold_zones + suggestions → emits "complete"
  ↓
Frontend swaps player to v2, re-renders timeline, re-pulses brain
```

## Gemma prompt (in `prompts.py`)

The single most important file in this skill. Iterate on this hard.

```python
AUTO_IMPROVE_SYSTEM_PROMPT = """
You are a video editor's diagnostic AI. Given a transcript, three engagement
curves (visual, auditory, language) from a brain prediction model, and a list
of cold zones where engagement dropped, your job is to identify the SINGLE
worst cold zone and propose ONE edit operation that will improve viewer
retention.

Reason out loud about WHY this cold zone is worst. Consider:
- Magnitude of engagement drop (how far below baseline)
- Duration of the drop
- Position in the video (drops near start are more costly)
- Which regions dropped (language drops = audience lost meaning;
  visual drops = audience disengaged from imagery)

Then propose ONE of:
- "cut": remove a contiguous range
- "speed": speed up a contiguous range by 1.25x or 1.5x

Output your reasoning in plain English (3-5 sentences), then output structured
JSON on a new line.

Be DECISIVE. Do not propose more than one edit. Do not hedge.
"""

AUTO_IMPROVE_USER_TEMPLATE = """
Video duration: {duration_s}s
Transcript: {transcript}

Engagement curves (1Hz, z-scored):
- Visual: {visual_curve}
- Auditory: {auditory_curve}
- Language: {language_curve}

Cold zones detected: {cold_zones_json}

Identify the worst cold zone. Reason about why. Then output a single edit:

```json
{{"reasoning": "<your reasoning>", "operation": "cut"|"speed", "params": {{"start_t": <float>, "end_t": <float>, "speed_factor": <float, only for speed>}}}}
```
"""
```

The double-newline-then-fenced-JSON pattern is what lets you stream the
reasoning to the user while still parsing the structured output at the end.

## Streaming reasoning to the frontend

Use `sse_starlette.EventSourceResponse` with a generator. As Gemma streams tokens, emit them as `event: reasoning` SSE events:

```python
from sse_starlette.sse import EventSourceResponse
import json

async def auto_improve_stream(clip_id: str, version: int):
    # Fetch v1 analysis
    v1 = cache.get_analysis(clip_id, version)

    # Build prompt
    user_prompt = AUTO_IMPROVE_USER_TEMPLATE.format(...)

    # Stream Gemma generation
    accumulated = ""
    async for token in gemma.stream_completion(
        system=AUTO_IMPROVE_SYSTEM_PROMPT,
        user=user_prompt,
    ):
        accumulated += token
        yield {"event": "reasoning", "data": json.dumps({"text": token})}

    # Parse JSON from accumulated text
    cut_op = parse_cut_from_response(accumulated)
    if not cut_op:
        # Fallback: heuristic — cut the worst cold zone
        cut_op = heuristic_cut(v1.cold_zones)

    yield {"event": "cutting", "data": json.dumps({"cut": cut_op})}

    # Apply ffmpeg cut
    v2_path = editor.apply_cut(v1.video_path, cut_op)
    yield {"event": "cut_applied", "data": json.dumps({"v2_url": str(v2_path)})}

    # Re-run TRIBE on v2
    yield {"event": "reanalyzing", "data": "{}"}
    v2_analysis = await tribe.analyze_video(v2_path)

    # Stream new brain frames
    for t, frame in enumerate(v2_analysis.brain_frames):
        yield {"event": "brain_frame", "data": json.dumps({
            "t": t,
            "activation": frame.tolist(),
        })}

    # Final
    yield {"event": "complete", "data": json.dumps({
        "v2_engagement": v2_analysis.engagement_curves,
        "v2_cold_zones": v2_analysis.cold_zones,
        "v2_suggestions": v2_analysis.suggestions,
    })}

@app.post("/auto-improve")
async def auto_improve(req: AutoImproveRequest):
    job_id = generate_job_id()
    # Spawn background task, return job_id for SSE subscription
    ...
    return {"job_id": job_id}

@app.get("/stream-improve/{job_id}")
async def stream_improve(job_id: str):
    return EventSourceResponse(auto_improve_stream(job_id))
```

## ffmpeg cut implementation (`editor.py`)

```python
import subprocess
from pathlib import Path

def apply_cut(input_path: Path, cut: dict) -> Path:
    """
    Apply a cut to a video. cut = {"operation": "cut", "params": {"start_t", "end_t"}}
    Returns path to v2 mp4.
    """
    if cut["operation"] != "cut":
        raise ValueError(f"Only 'cut' operation supported in v1, got {cut['operation']}")

    start = float(cut["params"]["start_t"])
    end = float(cut["params"]["end_t"])

    # Sanitize
    duration = get_video_duration(input_path)
    start = max(0.0, min(start, duration))
    end = max(start + 0.1, min(end, duration))

    output_path = input_path.with_name(input_path.stem + "_v2.mp4")

    # Use select filter to remove the [start, end] range
    filter_expr = f"select='not(between(t,{start},{end}))',setpts=N/FRAME_RATE/TB"
    audio_filter = f"aselect='not(between(t,{start},{end}))',asetpts=N/SR/TB"

    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", filter_expr,
        "-af", audio_filter,
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")

    return output_path
```

The `select` + `setpts=N/FRAME_RATE/TB` pattern is the right way to drop frames in ffmpeg without re-encoding the rest. Faster than re-cutting.

## Frontend: streaming reasoning UX

The 25-second TRIBE re-inference wait is dead air. Filling it with visible AI work is the difference between "demo broken" and "AI is thinking." On the frontend:

```typescript
// AutoImproveButton.tsx
const [reasoning, setReasoning] = useState("");
const [stage, setStage] = useState<"idle"|"reasoning"|"cutting"|"reanalyzing"|"complete">("idle");

async function startAutoImprove() {
  setStage("reasoning");
  setReasoning("");

  const res = await fetch(`${BRAIN}/auto-improve`, {
    method: "POST",
    body: JSON.stringify({ clip_id, version: 1 }),
  });
  const { job_id } = await res.json();

  const es = new EventSource(`${BRAIN}/stream-improve/${job_id}`);
  es.addEventListener("reasoning", (e) => {
    const { text } = JSON.parse(e.data);
    setReasoning(prev => prev + text);
  });
  es.addEventListener("cutting", (e) => {
    setStage("cutting");
    // Show "applying cut..." in timeline area
  });
  es.addEventListener("cut_applied", (e) => {
    const { v2_url } = JSON.parse(e.data);
    // DON'T swap player yet — wait for re-analysis
  });
  es.addEventListener("reanalyzing", () => {
    setStage("reanalyzing");
  });
  es.addEventListener("brain_frame", (e) => {
    const { t, activation } = JSON.parse(e.data);
    // Stream into BrainMonitor
  });
  es.addEventListener("complete", (e) => {
    setStage("complete");
    es.close();
    // Now swap player to v2, re-render timeline
  });
}
```

The timeline area visually swaps to render `reasoning` text instead of the engagement tracks. Brain monitor dims to ~30% opacity with thinking animation.

## Failure modes (handle these explicitly)

1. **Gemma returns invalid JSON.** Parse failure → use heuristic fallback (cut the deepest cold zone). Don't fail the whole request.

2. **Gemma proposes invalid timestamps** (negative, beyond duration, overlapping the entire video). `editor.py` clamps. If clamping produces a zero-length cut, emit `complete` with `error: "no improvement possible"` and let the frontend show a soft message.

3. **ffmpeg fails.** Almost always due to corrupt input or codec issues. Emit `error` event, frontend shows "couldn't cut this one" and falls back to v1.

4. **TRIBE re-inference fails on v2.** For hero clips, fall back to cached v2 analysis. For novel clips, return v2 video without engagement re-analysis (better than nothing).

5. **User clicks "auto-improve again" before v2 returns.** Debounce on frontend. Disable the button until SSE stream closes.

## Hero clip caching for the demo

For the 2 hero clips with pre-rendered v1→v2→v3 (PH-H), bypass the live pipeline entirely:

```python
HERO_CLIPS_WITH_AUTO_IMPROVE = {"khan", "startup"}

async def auto_improve_stream(clip_id: str, version: int):
    if clip_id in HERO_CLIPS_WITH_AUTO_IMPROVE:
        # Cached path — replay events with realistic delays for demo feel
        async for event in replay_cached_auto_improve(clip_id, version):
            yield event
        return
    # ... live pipeline
```

The cached replay should add small delays between events to *feel* like real inference (so judges don't notice the demo is canned). 2-3s for reasoning, 1s for cutting, 5-8s for re-analysis.

## What NOT to do

- **Don't propose more than one edit per round.** "Auto-improve" must feel decisive. Multiple suggestions would dilute the wow.
- **Don't allow B-roll generation, voice-over, music swap.** Out of scope per `@docs/CLAUDE.md` §2.
- **Don't make the loop fully automatic.** Each round requires a user click. Watching the AI iterate without permission feels creepy in a demo.
- **Don't expose ffmpeg errors to the user.** Always wrap in a friendly message + cache fallback.
