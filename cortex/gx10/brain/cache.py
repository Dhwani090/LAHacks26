# Filesystem JSON cache + in-memory hero clip preload.
# PRD §12 (cache + fallback) + §8.4 verification.
# In-memory dict for live request hashes; filesystem under cache/ for hero clips.
# NO Chroma, NO SQLite per CLAUDE.md §2.
# See docs/PRD.md §12.

from __future__ import annotations
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from . import config

logger = logging.getLogger(__name__)


class HeroCache:
    """Loads pre-rendered hero JSONs at startup; in-memory dict thereafter."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._live: dict[str, dict[str, Any]] = {}

    def load_heroes(self) -> int:
        count = 0
        for sub in (config.HERO_TEXT_DIR, config.HERO_AUDIO_DIR, config.HERO_VIDEO_DIR):
            if not sub.exists():
                continue
            for fp in sub.glob("*.json"):
                try:
                    with fp.open("r", encoding="utf-8") as f:
                        payload = json.load(f)
                    key = f"{sub.name}:{fp.stem}"
                    self._store[key] = payload
                    count += 1
                except Exception as exc:
                    logger.error("hero load failed for %s: %s", fp, exc)
        logger.info("loaded %d hero clips", count)
        return count

    def get_hero(self, mode: str, slug: str) -> dict[str, Any] | None:
        return self._store.get(f"hero_{mode}:{slug}")

    @staticmethod
    def hash_payload(payload: bytes | str) -> str:
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]

    def get_live(self, key: str) -> dict[str, Any] | None:
        return self._live.get(key)

    def put_live(self, key: str, value: dict[str, Any]) -> None:
        self._live[key] = value

    def size(self) -> int:
        return len(self._store) + len(self._live)


hero_cache = HeroCache()
