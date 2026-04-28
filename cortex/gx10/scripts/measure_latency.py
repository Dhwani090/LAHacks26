#!/usr/bin/env python3
# Measure cold + warm wall-clock latency for TRIBE text/audio/video inference.
# PRD §6 latency budgets, P1-01 verification step C.
# Loads TRIBE once, runs each modality twice (first = cold, second = warm),
# and writes the numbers to cortex/spikes/tribe_latency.md.
#
# Usage (from cortex/gx10):
#   python scripts/measure_latency.py [--audio path.m4a] [--video path.mp4]
#
# `uvx` must be on PATH (cortexlab shells out for whisperx alignment).
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Ensure ~/.local/bin (uvx) is reachable when run via plain bash -c.
os.environ["PATH"] = os.path.expanduser("~/.local/bin") + ":" + os.environ.get("PATH", "")

# Make `from brain.tribe import ...` resolvable when run from gx10/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brain import config  # noqa: E402
from brain.tribe import TribeService  # noqa: E402

TEXT_SAMPLE = (
    "Most creators ship work and wait two weeks for analytics to know if it landed. "
    "We don't. The model says the average reader checked out on the middle sentence. "
    "Five-second iteration: edit, see the brain, edit again."
)


def time_call(label: str, fn) -> tuple[float, str]:
    t0 = time.perf_counter()
    try:
        fn()
        elapsed = time.perf_counter() - t0
        return elapsed, "ok"
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        return elapsed, f"FAILED: {exc}"


def fmt(rows: list[tuple[str, str, float, str]]) -> str:
    lines = [
        "# TRIBE latency",
        "",
        "Wall-clock seconds, single run on the GX10. `cold` = first call after",
        "process start (model layers may be paged but the per-call caches are empty).",
        "`warm` = the same call repeated immediately after.",
        "",
        "| mode | phase | seconds | status |",
        "|---|---|---|---|",
    ]
    for mode, phase, seconds, status in rows:
        lines.append(f"| {mode} | {phase} | {seconds:.2f} | {status} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", type=Path, default=None, help="audio clip (mp3/wav/m4a)")
    ap.add_argument("--video", type=Path, default=None, help="video clip (mp4/mov)")
    ap.add_argument(
        "--out",
        type=Path,
        default=config.GX10_ROOT.parent / "spikes" / "tribe_latency.md",
    )
    args = ap.parse_args()

    svc = TribeService()
    t_load = time.perf_counter()
    svc.load()  # warmup runs inside load() — first text call is paid here
    load_s = time.perf_counter() - t_load
    if not svc.loaded or svc._model is None:
        print("TRIBE failed to load — see logs.", file=sys.stderr)
        return 1
    print(f"[measure] load+warmup: {load_s:.2f}s")

    rows: list[tuple[str, str, float, str]] = [("load+warmup", "—", load_s, "ok")]

    # Text: cold = first non-warmup call; warm = the call after that.
    for phase in ("cold", "warm"):
        s, status = time_call(f"text/{phase}", lambda: svc.analyze_text(TEXT_SAMPLE))
        print(f"[measure] text/{phase}: {s:.2f}s ({status})")
        rows.append(("text", phase, s, status))

    if args.audio is not None and args.audio.exists():
        for phase in ("cold", "warm"):
            s, status = time_call(
                f"audio/{phase}", lambda p=args.audio: svc.analyze_audio(p)
            )
            print(f"[measure] audio/{phase}: {s:.2f}s ({status})")
            rows.append(("audio", phase, s, status))
    else:
        rows.append(("audio", "skipped", 0.0, "no --audio path provided"))

    if args.video is not None and args.video.exists():
        for phase in ("cold", "warm"):
            s, status = time_call(
                f"video/{phase}", lambda p=args.video: svc.analyze_video(p)
            )
            print(f"[measure] video/{phase}: {s:.2f}s ({status})")
            rows.append(("video", phase, s, status))
    else:
        rows.append(("video", "skipped", 0.0, "no --video path provided"))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(fmt(rows), encoding="utf-8")
    print(f"[measure] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
