# corpus.jsonl — training corpus + percentile-rank reference for engagement prediction.
# PRD §11.3 + skills/engagement-prediction/SKILL.md.
# One JSON object per line: {video_id, source, duration_s, followers, views, likes,
# comments, engagement_rate, tribe_features, ...}. Read once at startup; rates kept
# sorted in memory for O(log N) percentile lookup.
# See .claude/skills/engagement-prediction/SKILL.md §"Percentile rank".

from __future__ import annotations
import bisect
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_FOLLOWERS_FALLBACK = 10_000


class Corpus:
    """In-memory snapshot of corpus.jsonl. Reload by calling `load()` again."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._rows: list[dict[str, Any]] = []
        self._sorted_rates: list[float] = []

    def load(self, path: Path | None = None) -> int:
        if path is not None:
            self._path = path
        target = self._path
        self._rows = []
        self._sorted_rates = []
        if target is None or not target.exists():
            logger.warning("corpus path missing or unset: %s", target)
            return 0
        with target.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.warning("corpus line %d: bad JSON: %s", line_no, exc)
                    continue
                rate = row.get("engagement_rate")
                if not isinstance(rate, (int, float)):
                    continue
                self._rows.append(row)
                self._sorted_rates.append(float(rate))
        self._sorted_rates.sort()
        logger.info("corpus loaded: %d rows from %s", len(self._rows), target)
        return len(self._rows)

    def size(self) -> int:
        return len(self._rows)

    def rows(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def percentile(self, rate: float) -> int:
        """Returns 0–100 percentile rank of `rate` against the corpus.

        Empty corpus → 50 (median fallback so the UI still renders something).
        """
        if not self._sorted_rates:
            return 50
        idx = bisect.bisect_left(self._sorted_rates, rate)
        return max(0, min(100, int(round(100 * idx / len(self._sorted_rates)))))

    def median_followers(self) -> int:
        followers = sorted(
            int(r["followers"]) for r in self._rows
            if isinstance(r.get("followers"), (int, float)) and r["followers"] > 0
        )
        if not followers:
            return DEFAULT_FOLLOWERS_FALLBACK
        return followers[len(followers) // 2]


corpus = Corpus()
