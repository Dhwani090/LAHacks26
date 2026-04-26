#!/usr/bin/env python3
"""One-machine ingest: yt-dlp + TRIBE + corpus append in one pass.

PRD §11.4 + .claude/skills/engagement-prediction/SKILL.md §"yt-dlp invocation patterns".

This is the "do it all on the GX10" path. For the Mac+GX10 split (download on a Mac
while the box is busy, then process), use `download_shorts.py` + `process_downloads.py`
instead.

Per-URL flow:
  yt-dlp -j --skip-download <url>       → metadata
  yt-dlp -f mp4 -o <id>.mp4 <url>       → video file
  TribeService.analyze_video(<path>)    → brain_frames + cold_zones
  pooling.frames_to_array + pool_tribe_output → 21-dim vector
  brain.ingest.build_corpus_row → row appended to cache/corpus.jsonl

Usage:
    python scripts/ingest_shorts.py path/to/seed_urls.txt
    python scripts/ingest_shorts.py --url https://www.youtube.com/shorts/<id>

Env:
    CORTEX_STUB_TRIBE=1   skip the real model load (laptop dev)
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import logging
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# Allow `from brain import ...` when run from cortex/gx10/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brain import config  # noqa: E402
from brain.ingest import append_corpus_row, build_corpus_row, read_existing_video_ids  # noqa: E402
from brain.pooling import frames_to_array, pool_tribe_output  # noqa: E402
from brain.tribe import tribe_service  # noqa: E402

logger = logging.getLogger("ingest_shorts")


def _yt_dlp_cmd() -> list[str]:
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    binary = shutil.which("yt-dlp")
    if binary:
        return [binary]
    raise RuntimeError("yt-dlp not importable and not on PATH — pip install yt-dlp")


_YT_DLP = _yt_dlp_cmd()


def _yt_dlp_metadata(url: str) -> dict[str, Any]:
    r = subprocess.run(
        [*_YT_DLP, "-j", "--skip-download", url],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp metadata failed for {url}: {r.stderr[:300]}")
    return json.loads(r.stdout)


def _yt_dlp_download(url: str, out_dir: Path) -> Path:
    out_template = str(out_dir / "%(id)s.%(ext)s")
    r = subprocess.run(
        [*_YT_DLP, "-f", "mp4/best", "-o", out_template, url],
        capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp download failed for {url}: {r.stderr[:300]}")
    candidates = sorted(
        [p for p in out_dir.iterdir() if p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}],
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if not candidates:
        raise RuntimeError(f"yt-dlp succeeded but no media file in {out_dir}")
    return candidates[0]


def ingest_one(url: str, out_dir: Path) -> dict[str, Any] | None:
    meta = _yt_dlp_metadata(url)
    video_path = _yt_dlp_download(url, out_dir)
    result = tribe_service.analyze_video(video_path)
    preds = frames_to_array(result["brain_frames"])
    pooled = pool_tribe_output(preds)
    return build_corpus_row(meta, pooled, len(result.get("cold_zones") or []))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("urls_file", nargs="?", help="text file with one URL per line")
    p.add_argument("--url", action="append", default=[], help="explicit URL (repeatable)")
    p.add_argument("--corpus", type=Path, default=config.CACHE_DIR / "corpus.jsonl")
    p.add_argument("--sleep", type=float, default=1.0, help="seconds between URLs")
    args = p.parse_args()

    urls: list[str] = list(args.url)
    if args.urls_file:
        urls.extend(
            line.strip() for line in Path(args.urls_file).read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    if not urls:
        p.error("no URLs given (pass a urls file or --url)")

    tribe_service.load()
    existing = read_existing_video_ids(args.corpus)

    ok, skipped, failed = 0, 0, 0
    with tempfile.TemporaryDirectory(prefix="cortex_ingest_") as tmp:
        tmp_dir = Path(tmp)
        for i, url in enumerate(urls, 1):
            logger.info("[%d/%d] %s", i, len(urls), url)
            try:
                row = ingest_one(url, tmp_dir)
            except Exception as exc:
                logger.error("ingest failed: %s", exc)
                failed += 1
                continue
            if row is None:
                skipped += 1
                continue
            if row["video_id"] in existing:
                logger.info("  already in corpus, skipping")
                skipped += 1
                continue
            append_corpus_row(args.corpus, row)
            existing.add(row["video_id"])
            ok += 1
            if args.sleep > 0 and i < len(urls):
                time.sleep(args.sleep)

    logger.info("done: ok=%d skipped=%d failed=%d → %s", ok, skipped, failed, args.corpus)
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
