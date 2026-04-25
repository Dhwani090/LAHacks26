# ffmpeg cut wrapper — pure function, no global state.
# PRD §8.3 + skills/auto-improve/SKILL.md.
# Sanitizes timestamps; uses select+setpts to drop frames without re-encoding the rest.
# See .claude/skills/auto-improve/SKILL.md for the filter pattern.
# Real path resolution + tests land in P2-05.

from __future__ import annotations
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_video_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(json.loads(result.stdout)["format"]["duration"])


def apply_cut(input_path: Path, cut: dict[str, Any]) -> Path:
    """Apply a cut. cut = {"operation":"cut","params":{"start_t":..,"end_t":..}}.

    Returns path to output mp4. Raises RuntimeError on ffmpeg failure.
    """
    if cut.get("operation") != "cut":
        raise ValueError(f"Only 'cut' supported, got {cut.get('operation')}")

    start = float(cut["params"]["start_t"])
    end = float(cut["params"]["end_t"])

    duration = get_video_duration(input_path)
    start = max(0.0, min(start, duration))
    end = max(start + 0.1, min(end, duration))

    output_path = input_path.with_name(input_path.stem + "_v2.mp4")

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
        logger.error("ffmpeg failed: %s", result.stderr)
        raise RuntimeError(f"ffmpeg failed: {result.stderr[:500]}")

    return output_path
