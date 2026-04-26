# Shared ingest helpers — corpus row construction + dedup.
# PRD §11.3,§11.4 + skills/engagement-prediction/SKILL.md.
# Imported by scripts/ingest_shorts.py (one-machine) AND scripts/process_downloads.py (GX10
# half of the two-phase Mac+GX10 split). Pure-Python; numpy is the only heavy dep.
# See .claude/skills/engagement-prediction/SKILL.md.

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def build_corpus_row(
    meta: dict[str, Any],
    pooled: np.ndarray,
    n_cold_zones: int,
    source: str = "youtube_shorts",
) -> dict[str, Any] | None:
    """Build a corpus.jsonl row from yt-dlp metadata + pooled TRIBE features.

    Returns None (and logs why) when the metadata is missing required fields.
    """
    views = meta.get("view_count")
    followers = meta.get("channel_follower_count") or meta.get("uploader_subscriber_count")
    duration = meta.get("duration")
    vid = meta.get("id")

    if not isinstance(views, (int, float)) or views <= 0:
        logger.warning("skip %s: missing/zero view_count", vid)
        return None
    if not isinstance(followers, (int, float)) or followers <= 0:
        logger.warning("skip %s: missing channel_follower_count", vid)
        return None
    if not isinstance(duration, (int, float)) or duration <= 0:
        logger.warning("skip %s: missing duration", vid)
        return None

    return {
        "video_id": f"yt:{vid}",
        "source": source,
        "url": meta.get("webpage_url") or meta.get("original_url"),
        "uploader": meta.get("uploader") or meta.get("channel"),
        "duration_s": float(duration),
        "followers": int(followers),
        "views": int(views),
        "likes": int(meta.get("like_count") or 0),
        "comments": int(meta.get("comment_count") or 0),
        "engagement_rate": float(views) / float(followers),
        "tribe_features": pooled.tolist(),
        "n_cold_zones": int(n_cold_zones),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "predictor_version": None,
    }


def read_existing_video_ids(corpus_path: Path) -> set[str]:
    """Return the set of `video_id` values already present in corpus.jsonl.

    Used by ingestion scripts to skip videos that have already been processed.
    Empty set if the file doesn't exist or has no parseable rows.
    """
    if not corpus_path.exists():
        return set()
    out: set[str] = set()
    with corpus_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            vid = row.get("video_id")
            if isinstance(vid, str) and vid:
                out.add(vid)
    return out


def append_corpus_row(corpus_path: Path, row: dict[str, Any]) -> None:
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    with corpus_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
