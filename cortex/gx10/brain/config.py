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
