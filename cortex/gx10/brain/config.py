# Magic numbers — backend single source.
# CLAUDE.md §4 mandates this file holds every tuning constant.
# Frontend mirror: cortex/web/src/app/lib/tuning.ts.
# See docs/PRD.md §10 for activation colormap context.

from pathlib import Path

# Paths
GX10_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = GX10_ROOT / "cache"
HERO_TEXT_DIR = CACHE_DIR / "hero_text"
HERO_AUDIO_DIR = CACHE_DIR / "hero_audio"
HERO_VIDEO_DIR = CACHE_DIR / "hero_video"

# TRIBE
TRIBE_MODEL_ID = "facebook/tribev2"
TRIBE_FRAME_RATE_HZ = 1.0
TRIBE_VERTEX_COUNT = 20484

# Clip duration ceiling — covers YT Shorts max (180s), IG Reels max (90s), and most TikToks.
# Anything longer is rejected at the upload boundary (PRD §2 hard non-goal).
MAX_CLIP_DURATION_S = 180

# Similarity (PRD §11.6) — creator's personal library, brain + transcript fusion.
SIMILARITY_BRAIN_WEIGHT = 0.6
SIMILARITY_TEXT_WEIGHT = 0.4
SIMILARITY_TOP_K = 3
SIMILARITY_MIN_LIBRARY_SIZE = 5

# Cold zones (skill: tribe-inference)
COLD_THRESHOLD_Z = -0.5
COLD_MIN_DURATION_S = 2.0

# Latency budgets (PRD §6)
TEXT_BUDGET_S = 12
AUDIO_BUDGET_S = 18
VIDEO_BUDGET_S = 45

# Network
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8080

# Gemma
GEMMA_MODEL_ID = "google/gemma-2-2b-it"
GEMMA_MAX_NEW_TOKENS = 512
GEMMA_TEMPERATURE = 0.7

# Curator (PRD §11.7) — idle-time NemoClaw active-learning agent.
# Iteration body is a no-op until R-02; constants live here so R-02/R-03 inherit them.
CURATOR_POLL_INTERVAL_S = 30  # priority-gate sleep when active streams > 0 OR not enabled
CURATOR_TICK_INTERVAL_S = 60  # idle wait between iterations when no work to do
CURATOR_ITERATIONS_PER_TRENDING = 6  # iter_count % N == N-1 → trending iteration
CURATOR_ENABLED_FILE = CACHE_DIR / "curator.enabled"  # opt-in master gate (off by default)
CURATOR_DISABLED_FILE = CACHE_DIR / "curator.disabled"  # runtime kill switch (precedence)
CURATOR_LOG_FILE = CACHE_DIR / "curator_log.jsonl"
CURATOR_QUERY_POOL_FILE = CACHE_DIR / "curator_query_pool.jsonl"
# Cold-start gate (PRD §11.7) — switch from bootstrap queries to gap-driven Gemma
# queries once both thresholds are met. Either condition holding → still cold.
CURATOR_COLD_R2_THRESHOLD = 0.05
CURATOR_COLD_CORPUS_THRESHOLD = 100
# Query counts per iteration. 5 gap-driven queries × 20 ytsearch results = 100
# candidate URLs per warm iteration; bootstrap stays smaller while we learn.
CURATOR_BOOTSTRAP_QUERIES_PER_ITER = 3
CURATOR_GAP_QUERIES_PER_ITER = 5
CURATOR_TRENDING_QUERIES_PER_ITER = 1
# Probability per corpus iteration of augmenting with one self-supervised query
# from cache/curator_query_pool.jsonl (R-03 fills the pool, R-02 only reads it).
CURATOR_QUERY_POOL_SAMPLE_RATE = 0.10
CURATOR_QUERY_POOL_MAX_SIZE = 200
