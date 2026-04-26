#!/usr/bin/env python3
"""Phase 2 of the two-phase corpus build (GX10-runnable, TRIBE inference).

PRD §11.3,§11.4 + .claude/skills/engagement-prediction/SKILL.md.

Reads a directory populated by `download_shorts.py` (run on a Mac while the GX10 was
busy) and, for each `<id>.mp4` + `<id>.meta.json` pair, runs TRIBE inference, pools
the output to a 21-dim feature vector, and appends a row to `cache/corpus.jsonl`.

Idempotent: ids already present in corpus.jsonl are skipped. Re-run after adding more
downloads and it only processes the new ones.

Usage:
    # On the GX10, after rsync from the Mac:
    python scripts/process_downloads.py --in-dir ~/cortex_downloads/

    # Override corpus path or process a single video:
    python scripts/process_downloads.py --in-dir downloads/ --corpus cache/corpus.jsonl
    python scripts/process_downloads.py --in-dir downloads/ --only abc123
"""
from __future__ import annotations
import argparse
import json
import logging
import sys
from pathlib import Path

# Allow `from brain import ...` when run from cortex/gx10/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brain import config  # noqa: E402
from brain.ingest import append_corpus_row, build_corpus_row, read_existing_video_ids  # noqa: E402
from brain.pooling import frames_to_array, pool_tribe_output  # noqa: E402
from brain.tribe import tribe_service  # noqa: E402

logger = logging.getLogger("process_downloads")


_MEDIA_EXTS = {".mp4", ".mkv", ".webm", ".mov"}


def find_pairs(in_dir: Path) -> list[tuple[str, Path, Path]]:
    """Return [(video_id, media_path, meta_path), ...] for every well-formed pair in in_dir."""
    pairs: list[tuple[str, Path, Path]] = []
    seen: set[str] = set()
    for media in sorted(in_dir.iterdir()):
        if media.suffix.lower() not in _MEDIA_EXTS:
            continue
        vid = media.stem
        if vid in seen:
            continue
        meta_path = in_dir / f"{vid}.meta.json"
        if not meta_path.exists():
            logger.warning("skip %s: no .meta.json sidecar", media.name)
            continue
        pairs.append((vid, media, meta_path))
        seen.add(vid)
    return pairs


def process_one(media_path: Path, meta_path: Path) -> dict | None:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    result = tribe_service.analyze_video(media_path)
    preds = frames_to_array(result["brain_frames"])
    pooled = pool_tribe_output(preds)
    return build_corpus_row(meta, pooled, n_cold_zones=len(result.get("cold_zones") or []))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--in-dir", type=Path, required=True, help="dir produced by download_shorts.py")
    p.add_argument("--corpus", type=Path, default=config.CACHE_DIR / "corpus.jsonl")
    p.add_argument("--only", help="process only a single video_id (the bare yt id, no `yt:` prefix)")
    p.add_argument("--no-skip", action="store_true", help="don't skip ids already in corpus")
    args = p.parse_args()

    if not args.in_dir.exists() or not args.in_dir.is_dir():
        logger.error("in-dir does not exist or is not a directory: %s", args.in_dir)
        return 1

    pairs = find_pairs(args.in_dir)
    if not pairs:
        logger.error("no <id>.mp4 + <id>.meta.json pairs found in %s", args.in_dir)
        return 1
    if args.only:
        pairs = [t for t in pairs if t[0] == args.only]
        if not pairs:
            logger.error("--only %s: no matching pair in %s", args.only, args.in_dir)
            return 1

    existing = set() if args.no_skip else read_existing_video_ids(args.corpus)
    logger.info("found %d pairs in %s; %d already in corpus", len(pairs), args.in_dir, len(existing))

    tribe_service.load()

    ok, skipped, failed = 0, 0, 0
    for i, (vid, media, meta_path) in enumerate(pairs, 1):
        full_id = f"yt:{vid}"
        if full_id in existing:
            logger.info("[%d/%d] %s: already in corpus, skipping", i, len(pairs), vid)
            skipped += 1
            continue
        logger.info("[%d/%d] %s (%s)", i, len(pairs), vid, media.name)
        try:
            row = process_one(media, meta_path)
        except Exception as exc:
            logger.error("  process failed: %s", exc)
            failed += 1
            continue
        if row is None:
            skipped += 1
            continue
        append_corpus_row(args.corpus, row)
        ok += 1

    logger.info("done: ok=%d skipped=%d failed=%d → %s", ok, skipped, failed, args.corpus)
    return 0 if ok > 0 else (0 if skipped > 0 else 1)


if __name__ == "__main__":
    raise SystemExit(main())
