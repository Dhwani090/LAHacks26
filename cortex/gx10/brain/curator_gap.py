# NemoClaw curator — query selection (PRD §11.7 "How the agent knows what to scrape").
# Three sources in priority order: (1) bootstrap niches when the predictor is cold,
# (2) gap-driven Gemma queries when the predictor is warm, (3) self-supervised query
# expansion sampled at low probability from cache/curator_query_pool.jsonl. Trending
# iterations short-circuit to TRENDING_QUERIES.
# See docs/PRD.md §11.7.

from __future__ import annotations
import json
import logging
import math
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config
from .corpus import Corpus
from .gemma import GemmaService
from .predictor import EngagementPredictor

logger = logging.getLogger(__name__)


# 12 diverse niches — sampled uniformly during cold start. Hand-picked to span the
# engagement-rate distribution and prevent the predictor from over-fitting one vertical.
BOOTSTRAP_QUERIES: tuple[str, ...] = (
    "cooking shorts",
    "fitness shorts",
    "explainer shorts",
    "comedy shorts",
    "beauty tutorial shorts",
    "gaming clip shorts",
    "dance shorts",
    "asmr shorts",
    "pitch shorts",
    "lifestyle shorts",
    "science shorts",
    "motivation shorts",
)

# Trending iteration uses these — same ytsearch20: mechanism, no separate API.
TRENDING_QUERIES: tuple[str, ...] = (
    "#shorts trending today",
    "#shortsoftheday viral",
    "#fyp shorts",
    "trending shorts this week",
    "viral shorts today",
)

# Engagement-rate bin edges for the density-only gap-finder. 8 bins covering the
# realistic Shorts range (0% to 50%+); top bin is open-ended.
_RATE_BIN_EDGES: tuple[float, ...] = (0.0, 0.02, 0.05, 0.08, 0.12, 0.18, 0.25, 0.35, 0.50)


@dataclass
class GapDescriptor:
    """Where the corpus is thinnest. R-02 emits density-only gaps; R-03 will swap
    in residual-variance once the predictor is real."""
    bin_label: str  # e.g., "0.18–0.25"
    bin_index: int
    bin_low: float
    bin_high: float
    bin_count: int  # how many corpus rows fell in this bin
    total_count: int
    confidence: float  # 0..1 — low when the corpus is too small to trust the gap
    is_empty_corpus: bool = False

    def to_prompt_phrase(self) -> str:
        """Phrasing for the Gemma prompt — kept human-readable so the model has
        an easy time turning it into search queries."""
        if self.is_empty_corpus:
            return "any short-form video that creators post (the corpus is empty)"
        return (
            f"YouTube Shorts with engagement rates between "
            f"{self.bin_low * 100:.0f}% and {self.bin_high * 100:.0f}% "
            f"(only {self.bin_count} of {self.total_count} clips in this band)"
        )


def is_cold_start(corpus: Corpus, predictor: EngagementPredictor) -> bool:
    """PRD §11.7 cold-start gate: corpus too small OR predictor R² too low (or unknown)."""
    if corpus.size() < config.CURATOR_COLD_CORPUS_THRESHOLD:
        return True
    r2 = getattr(predictor, "r2", None)
    if r2 is None:
        return True
    return r2 < config.CURATOR_COLD_R2_THRESHOLD


def find_gap(corpus: Corpus) -> GapDescriptor:
    """Density-only gap-finder. Bin engagement rates, find the bin with the fewest
    rows (excluding empty bins of course — wait, actually including them, since an
    empty bin IS the strongest gap signal).

    Confidence shrinks toward 0 when the corpus is small — a gap over 10 rows is noise."""
    rows = corpus.rows()
    if not rows:
        return GapDescriptor(
            bin_label="(empty)", bin_index=-1, bin_low=0.0, bin_high=0.0,
            bin_count=0, total_count=0, confidence=0.0, is_empty_corpus=True,
        )

    rates: list[float] = [
        float(r["engagement_rate"]) for r in rows
        if isinstance(r.get("engagement_rate"), (int, float))
    ]
    if not rates:
        return GapDescriptor(
            bin_label="(no rates)", bin_index=-1, bin_low=0.0, bin_high=0.0,
            bin_count=0, total_count=0, confidence=0.0, is_empty_corpus=True,
        )

    bin_counts: Counter[int] = Counter()
    for rate in rates:
        bin_counts[_bin_index(rate)] += 1

    # Find the most underrepresented bin among all _RATE_BIN_EDGES windows. Empty
    # bins win automatically (count = 0). If multiple tie, pick the lowest index
    # so the choice is deterministic per-corpus (helps tests).
    n_bins = len(_RATE_BIN_EDGES) - 1
    sparsest_idx = min(range(n_bins), key=lambda i: (bin_counts.get(i, 0), i))
    sparsest_count = bin_counts.get(sparsest_idx, 0)
    low = _RATE_BIN_EDGES[sparsest_idx]
    high = _RATE_BIN_EDGES[sparsest_idx + 1]

    # Confidence: corpus < 30 → near-zero; saturates around corpus = 200.
    confidence = 1.0 - math.exp(-len(rates) / 60.0)

    return GapDescriptor(
        bin_label=f"{low * 100:.0f}–{high * 100:.0f}%",
        bin_index=sparsest_idx,
        bin_low=low,
        bin_high=high,
        bin_count=sparsest_count,
        total_count=len(rates),
        confidence=round(confidence, 3),
    )


def _bin_index(rate: float) -> int:
    """Maps a rate in [0, ∞) to an index in [0, len(_RATE_BIN_EDGES) - 1)."""
    for i in range(len(_RATE_BIN_EDGES) - 1):
        if rate < _RATE_BIN_EDGES[i + 1]:
            return i
    return len(_RATE_BIN_EDGES) - 2  # everything above the top edge lands in the last bin


def _build_gemma_prompt(gap: GapDescriptor, k: int) -> str:
    return (
        "You are picking YouTube Shorts to fill a gap in a training corpus for an "
        "engagement-prediction model. Gap: " + gap.to_prompt_phrase() + ".\n"
        f"Output exactly {k} short search queries (under 8 words each), one per line, "
        "no numbering, no commentary. Each query should be plain English a YouTube "
        "search would understand. Focus on real creators and trending niches.\n"
        "Search queries:"
    )


def gemma_translate(
    gap: GapDescriptor,
    gemma: GemmaService,
    k: int,
    rng: random.Random | None = None,
) -> list[str]:
    """Turn a gap descriptor into k search queries via Gemma. Falls back to bootstrap
    queries if Gemma is unloaded or returns nothing usable — the caller should never
    crash because the model had a bad day. `rng` makes the fallback deterministic in tests."""
    if rng is None:
        rng = random.Random()
    prompt = _build_gemma_prompt(gap, k)
    text = gemma.generate(prompt, max_new_tokens=120)
    queries = _parse_queries(text, k=k)
    if not queries:
        logger.warning("curator_gap: Gemma returned no usable queries — falling back to bootstrap")
        # Clamp k to the bootstrap pool size — random.sample raises ValueError if k > population.
        return list(rng.sample(BOOTSTRAP_QUERIES, k=min(k, len(BOOTSTRAP_QUERIES))))
    return queries


# Punctuation Gemma sometimes trails a query with — strip from the right side only.
_TRAILING_PUNCT = ".,;:!?"


def _parse_queries(text: str, k: int) -> list[str]:
    """Extract up to k clean query strings from Gemma's raw output. Drops empty lines,
    leading bullets/numbers (single AND multi-digit), trailing punctuation, and
    lines obviously not queries."""
    if not text:
        return []
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        for prefix in ("- ", "* ", "• "):
            if s.startswith(prefix):
                s = s[len(prefix):].strip()
        # Strip leading "<digits><.|)> " — handles "1. ", "10. ", "100) ".
        i = 0
        while i < len(s) and s[i].isdigit():
            i += 1
        if 0 < i < len(s) and s[i] in ".)" and i + 1 < len(s) and s[i + 1] == " ":
            s = s[i + 2:].strip()
        s = s.rstrip(_TRAILING_PUNCT).strip()
        if not s or len(s) > 80 or len(s.split()) > 12:
            continue
        if s in out:
            continue
        out.append(s)
        if len(out) >= k:
            break
    return out


def _read_query_pool(path: Path | None) -> list[str]:
    """Returns recent self-supervised queries (R-03 produces them, R-02 only reads).
    Missing/unreadable file → empty list (no crash)."""
    if path is None or not path.exists():
        return []
    try:
        out: list[str] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                q = row.get("query")
                if isinstance(q, str) and q.strip():
                    out.append(q.strip())
        return out
    except OSError as exc:
        logger.warning("curator_gap: query pool read failed: %s", exc)
        return []


def pick_queries(
    iter_type: str,
    corpus: Corpus,
    predictor: EngagementPredictor,
    gemma: GemmaService,
    query_pool_path: Path | None = None,
    rng: random.Random | None = None,
) -> list[str]:
    """Three-source priority logic (PRD §11.7).

    Trending iterations short-circuit. Corpus iterations pick bootstrap or
    gap-driven Gemma queries based on cold-start, then optionally augment
    with one self-supervised query at CURATOR_QUERY_POOL_SAMPLE_RATE probability.
    """
    if rng is None:
        rng = random.Random()

    if iter_type == "trending":
        k = config.CURATOR_TRENDING_QUERIES_PER_ITER
        return list(rng.sample(TRENDING_QUERIES, k=min(k, len(TRENDING_QUERIES))))

    if iter_type != "corpus":
        # Defensive — should never happen, curator_loop only emits these two.
        logger.error("curator_gap: unknown iter_type=%r — returning bootstrap fallback", iter_type)
        return list(rng.sample(BOOTSTRAP_QUERIES, k=config.CURATOR_BOOTSTRAP_QUERIES_PER_ITER))

    if is_cold_start(corpus, predictor):
        queries = list(rng.sample(
            BOOTSTRAP_QUERIES,
            k=min(config.CURATOR_BOOTSTRAP_QUERIES_PER_ITER, len(BOOTSTRAP_QUERIES)),
        ))
    else:
        gap = find_gap(corpus)
        queries = gemma_translate(gap, gemma, k=config.CURATOR_GAP_QUERIES_PER_ITER, rng=rng)

    # Self-supervised augmentation — 10% of iterations sneak in one query learned
    # from past top-quartile transcripts. Empty pool → no-op.
    if rng.random() < config.CURATOR_QUERY_POOL_SAMPLE_RATE:
        pool = _read_query_pool(query_pool_path)
        if pool:
            extra = rng.choice(pool)
            if extra not in queries:
                queries.append(extra)

    return queries
