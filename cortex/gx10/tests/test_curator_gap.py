"""Tests for brain.curator_gap (PRD §11.7 query selection — R-02).

Covers cold-start detection, density-only gap-finder, Gemma stub translation,
self-supervised pool augmentation, and the three-source priority in pick_queries.
"""
from __future__ import annotations
import json
import os
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("CORTEX_STUB_TRIBE", "1")
os.environ["CORTEX_STUB_GEMMA"] = "1"
os.environ.setdefault("CORTEX_STUB_CURATOR", "1")

from brain import config, curator_gap  # noqa: E402
from brain.corpus import Corpus  # noqa: E402
from brain.gemma import gemma_service  # noqa: E402
from brain.predictor import EngagementPredictor  # noqa: E402


# Make sure Gemma stub is "loaded" so generate() doesn't return "" for being unloaded.
gemma_service._loaded = True


# ---------- constants ----------


def test_bootstrap_and_trending_queries_are_well_formed():
    assert len(curator_gap.BOOTSTRAP_QUERIES) >= 8
    assert all(isinstance(q, str) and q.strip() for q in curator_gap.BOOTSTRAP_QUERIES)
    assert len(set(curator_gap.BOOTSTRAP_QUERIES)) == len(curator_gap.BOOTSTRAP_QUERIES)
    assert len(curator_gap.TRENDING_QUERIES) >= 3
    assert all(isinstance(q, str) and q.strip() for q in curator_gap.TRENDING_QUERIES)
    assert len(set(curator_gap.TRENDING_QUERIES)) == len(curator_gap.TRENDING_QUERIES)


# ---------- cold-start gate ----------


def _stub_corpus(rates: list[float]) -> Corpus:
    """Build an in-memory Corpus from a list of engagement rates."""
    c = Corpus()
    c._rows = [{"engagement_rate": r} for r in rates]
    c._sorted_rates = sorted(rates)
    return c


def _stub_predictor(r2: float | None) -> EngagementPredictor:
    """Predictor with the given r2 marker (model identity doesn't matter for these tests)."""
    p = EngagementPredictor(model=object(), version="test")
    p.r2 = r2
    return p


def test_is_cold_start_empty_corpus():
    assert curator_gap.is_cold_start(_stub_corpus([]), _stub_predictor(0.5)) is True


def test_is_cold_start_corpus_below_threshold():
    rates = [0.05] * (config.CURATOR_COLD_CORPUS_THRESHOLD - 1)
    assert curator_gap.is_cold_start(_stub_corpus(rates), _stub_predictor(0.5)) is True


def test_is_cold_start_r2_none():
    rates = [0.05] * (config.CURATOR_COLD_CORPUS_THRESHOLD + 50)
    assert curator_gap.is_cold_start(_stub_corpus(rates), _stub_predictor(None)) is True


def test_is_cold_start_r2_below_threshold():
    rates = [0.05] * (config.CURATOR_COLD_CORPUS_THRESHOLD + 50)
    assert curator_gap.is_cold_start(_stub_corpus(rates), _stub_predictor(0.0)) is True


def test_is_cold_start_warm_predictor():
    rates = [0.05] * (config.CURATOR_COLD_CORPUS_THRESHOLD + 50)
    assert curator_gap.is_cold_start(_stub_corpus(rates), _stub_predictor(0.10)) is False


# ---------- gap-finder ----------


def test_find_gap_empty_corpus():
    gap = curator_gap.find_gap(_stub_corpus([]))
    assert gap.is_empty_corpus is True
    assert gap.confidence == 0.0
    assert "empty" in gap.to_prompt_phrase().lower()


def test_find_gap_uniform_density_low_confidence():
    # 30 rows spread evenly across bins → confidence stays moderate (~0.4).
    rates = [0.01, 0.03, 0.06, 0.10, 0.15, 0.20] * 5
    gap = curator_gap.find_gap(_stub_corpus(rates))
    assert gap.is_empty_corpus is False
    assert 0.0 < gap.confidence < 0.7  # under-saturated corpus → moderate confidence
    assert gap.bin_count <= len(rates) // 6 + 1  # most underrepresented bin


def test_find_gap_names_underrepresented_bin():
    # 200 rows that fill bins 0/1/2/3/6 and leave bins 4 (12–18%), 5 (18–25%),
    # 7 (35–50%) all empty. find_gap's deterministic tie-break (lowest index
    # wins on equal counts — see find_gap docstring) picks bin 4 = 12–18%.
    rates = (
        [0.005] * 40 + [0.03] * 40 + [0.06] * 40 + [0.10] * 40 + [0.30] * 40
    )
    gap = curator_gap.find_gap(_stub_corpus(rates))
    assert gap.bin_count == 0
    assert gap.bin_low == 0.12
    assert gap.bin_high == 0.18
    assert "12" in gap.bin_label and "18" in gap.bin_label
    assert gap.confidence > 0.9  # 200 rows → near-saturated confidence


# ---------- gemma_translate ----------


def test_gemma_translate_stub_returns_5_queries():
    gap = curator_gap.GapDescriptor(
        bin_label="18–25%", bin_index=5, bin_low=0.18, bin_high=0.25,
        bin_count=0, total_count=200, confidence=0.96,
    )
    queries = curator_gap.gemma_translate(gap, gemma_service, k=5)
    assert len(queries) == 5
    assert all(isinstance(q, str) and q.strip() for q in queries)
    assert len(set(queries)) == 5  # no dupes


def test_gemma_translate_falls_back_when_response_empty(monkeypatch):
    # Force generate() to return empty so the fallback path runs.
    monkeypatch.setattr(gemma_service, "generate", lambda prompt, max_new_tokens=128: "")
    gap = curator_gap.GapDescriptor(
        bin_label="0–2%", bin_index=0, bin_low=0.0, bin_high=0.02,
        bin_count=0, total_count=100, confidence=0.8,
    )
    queries = curator_gap.gemma_translate(gap, gemma_service, k=5)
    assert len(queries) == 5
    assert all(q in curator_gap.BOOTSTRAP_QUERIES for q in queries)


# ---------- pick_queries ----------


def test_pick_queries_trending_returns_one():
    rng = random.Random(0)
    out = curator_gap.pick_queries(
        iter_type="trending",
        corpus=_stub_corpus([]),
        predictor=_stub_predictor(None),
        gemma=gemma_service,
        query_pool_path=None,
        rng=rng,
    )
    assert len(out) == config.CURATOR_TRENDING_QUERIES_PER_ITER
    assert out[0] in curator_gap.TRENDING_QUERIES


def test_pick_queries_corpus_cold_start_returns_bootstrap():
    rng = random.Random(0)
    out = curator_gap.pick_queries(
        iter_type="corpus",
        corpus=_stub_corpus([]),
        predictor=_stub_predictor(None),
        gemma=gemma_service,
        query_pool_path=None,
        rng=rng,
    )
    assert len(out) == config.CURATOR_BOOTSTRAP_QUERIES_PER_ITER
    assert all(q in curator_gap.BOOTSTRAP_QUERIES for q in out)


def test_pick_queries_corpus_warm_uses_gemma():
    rates = [0.05] * (config.CURATOR_COLD_CORPUS_THRESHOLD + 50)
    rng = random.Random(0)
    out = curator_gap.pick_queries(
        iter_type="corpus",
        corpus=_stub_corpus(rates),
        predictor=_stub_predictor(0.10),
        gemma=gemma_service,
        query_pool_path=None,
        rng=rng,
    )
    # Stub Gemma returns 5 queries from _stub_response — none are in BOOTSTRAP_QUERIES.
    assert len(out) == config.CURATOR_GAP_QUERIES_PER_ITER
    assert any("hook" in q or "asmr" in q or "skit" in q or "explainer" in q for q in out)


def test_pick_queries_pool_augmentation_when_lucky(tmp_path):
    pool_path = tmp_path / "pool.jsonl"
    with pool_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"query": "self_supervised_test_query"}) + "\n")
    # rng.random() < 0.10 always when seeded so the augment branch triggers.
    class AlwaysAugment(random.Random):
        def random(self):
            return 0.0
    rng = AlwaysAugment(0)
    out = curator_gap.pick_queries(
        iter_type="corpus",
        corpus=_stub_corpus([]),  # cold start → bootstrap
        predictor=_stub_predictor(None),
        gemma=gemma_service,
        query_pool_path=pool_path,
        rng=rng,
    )
    assert "self_supervised_test_query" in out


def test_pick_queries_missing_pool_path_no_crash():
    rng = random.Random(0)
    out = curator_gap.pick_queries(
        iter_type="corpus",
        corpus=_stub_corpus([]),
        predictor=_stub_predictor(None),
        gemma=gemma_service,
        query_pool_path=Path("/tmp/definitely_does_not_exist_curator_pool.jsonl"),
        rng=rng,
    )
    # Cold start → 3 bootstrap queries, no augmentation (file missing → empty pool).
    assert len(out) == config.CURATOR_BOOTSTRAP_QUERIES_PER_ITER
    assert all(q in curator_gap.BOOTSTRAP_QUERIES for q in out)


# ---------- regression: parser hardening (caught by /qa on 2026-04-25) ----------


def test_parse_queries_strips_two_digit_numeric_prefix():
    # Regression: ISSUE-QA-17 — _parse_queries kept "10. ..." prefixes because the
    # original strip only handled single-digit. Multi-digit must work too.
    text = "1. cooking shorts\n10. asmr trending\n100) viral skit"
    out = curator_gap._parse_queries(text, k=10)
    assert out == ["cooking shorts", "asmr trending", "viral skit"]


def test_parse_queries_strips_trailing_punctuation():
    # Regression: ISSUE-QA-18 — trailing "." / "!" / "?" got passed through into
    # the yt-dlp query and made search results noisy.
    text = "viral asmr cooking shorts.\nfitness motivation!\nexplainer shorts?"
    out = curator_gap._parse_queries(text, k=5)
    assert out == ["viral asmr cooking shorts", "fitness motivation", "explainer shorts"]


def test_gemma_translate_fallback_clamps_k_when_oversize(monkeypatch):
    # Regression: ISSUE-QA-16 — random.sample raises ValueError if k > population.
    # The fallback path with k > len(BOOTSTRAP_QUERIES) used to crash; now it clamps.
    monkeypatch.setattr(gemma_service, "generate", lambda prompt, max_new_tokens=128: "")
    gap = curator_gap.GapDescriptor(
        bin_label="0–2%", bin_index=0, bin_low=0.0, bin_high=0.02,
        bin_count=0, total_count=100, confidence=0.8,
    )
    # Ask for 50 queries — way more than BOOTSTRAP_QUERIES (12). Must not raise.
    queries = curator_gap.gemma_translate(gap, gemma_service, k=50, rng=random.Random(0))
    assert 0 < len(queries) <= len(curator_gap.BOOTSTRAP_QUERIES)
    assert all(q in curator_gap.BOOTSTRAP_QUERIES for q in queries)


def test_gemma_translate_fallback_uses_injected_rng_for_determinism(monkeypatch):
    # Regression: ISSUE-QA-15 — fallback used module-level random, so repeat
    # invocations were non-deterministic even when the caller passed an rng.
    monkeypatch.setattr(gemma_service, "generate", lambda prompt, max_new_tokens=128: "")
    gap = curator_gap.GapDescriptor(
        bin_label="0–2%", bin_index=0, bin_low=0.0, bin_high=0.02,
        bin_count=0, total_count=100, confidence=0.8,
    )
    a = curator_gap.gemma_translate(gap, gemma_service, k=5, rng=random.Random(42))
    b = curator_gap.gemma_translate(gap, gemma_service, k=5, rng=random.Random(42))
    assert a == b, "same seed must produce same fallback queries"
