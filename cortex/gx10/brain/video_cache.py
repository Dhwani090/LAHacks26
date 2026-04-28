# Video analysis result cache — file-hash keyed pickle on disk.
# PRD §3 (backend) — vjepa2-vitg is the demo bottleneck (~11min for 50s clip on
# Blackwell at bf16). Re-uploads of the same clip should be instant.
# Hash is sha256 of file contents; payload is the full tribe_service result dict.
# See docs/PRD.md §9 (analyze/video).

from __future__ import annotations
import hashlib
import logging
import pickle
from pathlib import Path
from typing import Any

from . import config

logger = logging.getLogger(__name__)

_CACHE_DIR = config.CACHE_DIR / "video_results"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_path(digest: str) -> Path:
    return _CACHE_DIR / f"{digest}.pkl"


def get(digest: str) -> dict[str, Any] | None:
    path = _cache_path(digest)
    if not path.exists():
        return None
    try:
        with path.open("rb") as f:
            return pickle.load(f)
    except Exception as exc:
        logger.warning("video cache read failed for %s: %s", digest, exc)
        return None


def put(digest: str, result: dict[str, Any]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(digest)
    try:
        with path.open("wb") as f:
            pickle.dump(result, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info("video cache wrote %s (%.1f KB)", digest[:12], path.stat().st_size / 1024)
    except Exception as exc:
        logger.warning("video cache write failed for %s: %s", digest, exc)
