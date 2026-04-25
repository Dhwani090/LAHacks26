"""Tests for ffmpeg cut wrapper (P2-05).

Verification per @docs/TASKS.md P2-05: a 30s clip cut from 14-21s produces
a ~23s playable mp4. Tests are skipped when ffmpeg/ffprobe are not on PATH
(local laptop). They are intended to run on the GX10 inside the cortex env.
"""
from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brain.editor import apply_cut, get_video_duration  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")

pytestmark = pytest.mark.skipif(
    not (FFMPEG and FFPROBE),
    reason="ffmpeg/ffprobe required (run on GX10 cortex env)",
)


@pytest.fixture(scope="module")
def sample_video(tmp_path_factory) -> Path:
    """Generate a 30s synthetic video using ffmpeg's lavfi source."""
    out = tmp_path_factory.mktemp("editor") / "sample_30s.mp4"
    cmd = [
        FFMPEG, "-y", "-f", "lavfi", "-i", "testsrc=duration=30:size=320x240:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"ffmpeg gen failed: {res.stderr[:500]}"
    return out


def test_get_duration_matches_30s(sample_video: Path):
    d = get_video_duration(sample_video)
    assert 29.5 <= d <= 30.5, f"expected ~30s, got {d}"


def test_apply_cut_14_to_21_produces_23s(sample_video: Path):
    out = apply_cut(sample_video, {"operation": "cut", "params": {"start_t": 14.0, "end_t": 21.0}})
    assert out.exists(), "output mp4 missing"
    d = get_video_duration(out)
    # Source 30s minus 7s removed = 23s. Allow ±1s for keyframe alignment.
    assert 22.0 <= d <= 24.0, f"expected ~23s, got {d}"


def test_invalid_operation_rejected(sample_video: Path):
    with pytest.raises(ValueError):
        apply_cut(sample_video, {"operation": "blur", "params": {}})


def test_clamps_out_of_range_timestamps(sample_video: Path):
    # End past video duration is clamped; output should still play.
    out = apply_cut(sample_video, {"operation": "cut", "params": {"start_t": 25.0, "end_t": 9999.0}})
    assert out.exists()
    d = get_video_duration(out)
    # Original 30s minus ~5s tail removed = ~25s.
    assert 24.0 <= d <= 26.5, f"expected ~25s, got {d}"
