#!/usr/bin/env python3
"""Phase 1 of the two-phase corpus build (Mac-runnable, no TRIBE).

PRD §11.4 + .claude/skills/engagement-prediction/SKILL.md §"yt-dlp invocation patterns".

For each URL: fetch yt-dlp metadata → write `<id>.meta.json`, download mp4 → write `<id>.mp4`.
Stdlib + yt-dlp subprocess only — no numpy, no torch, no TRIBE. Runs anywhere `yt-dlp`
is on PATH.

Idempotent: if both `<id>.meta.json` and `<id>.mp4` already exist with nonzero size, the
URL is skipped. Re-run after a partial pull and it picks up where it stopped.

Usage:
    python scripts/download_shorts.py path/to/seed_urls.txt --out-dir downloads/
    python scripts/download_shorts.py --url <url> --out-dir downloads/

Hand off to the GX10:
    rsync -avz --progress downloads/ gx10:~/cortex_downloads/
    # then on the GX10:
    python scripts/process_downloads.py --in-dir ~/cortex_downloads/
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger("download_shorts")


_YT_DLP_CACHE: list[str] | None = None


def _yt_dlp_cmd() -> list[str]:
    """Return the command prefix for invoking yt-dlp. Resolved lazily (called from
    fetch_metadata / download_video, not at import time, so utility imports of this
    module don't fail when yt-dlp isn't installed)."""
    global _YT_DLP_CACHE
    if _YT_DLP_CACHE is not None:
        return _YT_DLP_CACHE
    if importlib.util.find_spec("yt_dlp") is not None:
        _YT_DLP_CACHE = [sys.executable, "-m", "yt_dlp"]
    else:
        binary = shutil.which("yt-dlp")
        if binary:
            _YT_DLP_CACHE = [binary]
        else:
            logger.error("yt-dlp not importable and not on PATH — `pip install yt-dlp`")
            sys.exit(2)
    return _YT_DLP_CACHE


def fetch_metadata(url: str) -> dict:
    r = subprocess.run(
        [*_yt_dlp_cmd(), "-j", "--skip-download", url],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp metadata failed: {r.stderr[:300]}")
    return json.loads(r.stdout)


def download_video(url: str, out_dir: Path, video_id: str) -> Path:
    """Download to <out_dir>/<id>.mp4 (or .mkv/.webm if mp4 isn't offered).

    yt-dlp picks the best available container; we accept whatever lands so a missing
    mp4-formatted variant doesn't hard-fail the pull.
    """
    template = str(out_dir / "%(id)s.%(ext)s")
    r = subprocess.run(
        [*_yt_dlp_cmd(), "-f", "mp4/best", "-o", template, url],
        capture_output=True, text=True, timeout=600,
    )
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp download failed: {r.stderr[:300]}")
    candidates = list(out_dir.glob(f"{video_id}.*"))
    media = [c for c in candidates if c.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}]
    if not media:
        raise RuntimeError(f"yt-dlp succeeded but no media file found for {video_id}")
    return media[0]


def already_downloaded(out_dir: Path, video_id: str) -> bool:
    meta_ok = (out_dir / f"{video_id}.meta.json").exists() and (out_dir / f"{video_id}.meta.json").stat().st_size > 0
    media = list(out_dir.glob(f"{video_id}.mp4")) + list(out_dir.glob(f"{video_id}.mkv")) + list(out_dir.glob(f"{video_id}.webm"))
    media_ok = any(p.stat().st_size > 0 for p in media)
    return meta_ok and media_ok


# Fields from yt-dlp's `-j` output that we actually want to persist. The raw output is
# ~80KB per video (most of that is `formats`, a list of every codec/resolution variant
# yt-dlp could have downloaded — irrelevant once the mp4 is on disk). This allowlist
# trims to ~2-3KB per video while keeping every field the predictor or future analysis
# would plausibly need.
KEEP_META_FIELDS = {
    "id", "webpage_url", "original_url", "channel_url", "uploader_url",
    "view_count", "like_count", "comment_count",
    "channel_follower_count", "uploader_subscriber_count",
    "channel", "uploader", "channel_id", "uploader_id",
    "duration", "width", "height", "fps", "aspect_ratio",
    "title", "description", "tags", "categories",
    "upload_date", "release_date", "release_timestamp", "timestamp",
    "language", "age_limit", "live_status", "availability",
    "extractor", "extractor_key",
}


def slim_metadata(meta: dict) -> dict:
    return {k: meta[k] for k in KEEP_META_FIELDS if k in meta}


def write_metadata(out_dir: Path, video_id: str, meta: dict) -> Path:
    p = out_dir / f"{video_id}.meta.json"
    p.write_text(json.dumps(slim_metadata(meta), indent=2), encoding="utf-8")
    return p


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("urls_file", nargs="?", help="text file with one URL per line")
    p.add_argument("--url", action="append", default=[], help="explicit URL (repeatable)")
    p.add_argument("--out-dir", type=Path, default=Path("downloads"),
                   help="dir to write <id>.mp4 + <id>.meta.json (default: ./downloads)")
    p.add_argument("--sleep", type=float, default=1.0, help="seconds between URLs (rate-limit kindness)")
    args = p.parse_args()

    logger.info("using yt-dlp via: %s", " ".join(_yt_dlp_cmd()))

    urls: list[str] = list(args.url)
    if args.urls_file:
        urls.extend(
            line.strip() for line in Path(args.urls_file).read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    if not urls:
        p.error("no URLs given (pass a urls file or --url)")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ok, skipped, failed = 0, 0, 0

    for i, url in enumerate(urls, 1):
        logger.info("[%d/%d] %s", i, len(urls), url)
        try:
            meta = fetch_metadata(url)
        except Exception as exc:
            logger.error("metadata failed: %s", exc)
            failed += 1
            continue

        vid = meta.get("id")
        if not isinstance(vid, str) or not vid:
            logger.error("metadata missing id, skipping")
            failed += 1
            continue

        if already_downloaded(args.out_dir, vid):
            logger.info("  already downloaded, skipping")
            skipped += 1
            continue

        write_metadata(args.out_dir, vid, meta)
        try:
            media = download_video(url, args.out_dir, vid)
        except Exception as exc:
            logger.error("download failed: %s", exc)
            (args.out_dir / f"{vid}.meta.json").unlink(missing_ok=True)  # don't leave half-state
            failed += 1
            continue

        logger.info("  ok: %s (%.1f MB)", media.name, media.stat().st_size / 1e6)
        ok += 1
        if args.sleep > 0 and i < len(urls):
            time.sleep(args.sleep)

    logger.info("done: ok=%d skipped=%d failed=%d → %s", ok, skipped, failed, args.out_dir)
    logger.info("transfer to GX10:  rsync -avz --progress %s/ gx10:~/cortex_downloads/", args.out_dir)
    return 0 if (ok + skipped) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
