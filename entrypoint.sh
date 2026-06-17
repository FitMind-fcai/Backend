#!/bin/bash
# FitMind API — container startup script
# Runs before uvicorn starts. All steps are idempotent.
#
# Environment variables (set in docker-compose or .env):
#   RESEED_DB=true          → wipe and re-import foods + exercises from CSV
#   REBUILD_VECTOR_DB=true  → force-rebuild ChromaDB from existing scraped JSON
#   SCRAPE_RESOURCES=true   → re-scrape merged_resources.csv before rebuilding
#                             (only used together with REBUILD_VECTOR_DB=true)
#
# Auto-detection (no env vars needed):
#   If merged_resources.csv has changed since the last build (MD5 differs),
#   resources are re-scraped and ChromaDB is rebuilt automatically.
set -e

echo ""
echo "======================================================"
echo "  FitMind API — Startup Initialization"
echo "======================================================"

# ── Step 0: Create tables + pgvector extension ────────────────────────────
echo ""
echo "[init] Creating database tables..."
python -c "
from dotenv import load_dotenv; load_dotenv()
from sqlalchemy import text
from app.db.database import engine, Base

# Import all models so Base.metadata knows about them
from app.auth_module.models.user import User
from app.profile_module.models.profile import *
from app.planning_module.models.plan import *
from app.tracking_module.models.workout_log import *
from app.tracking_module.models.meal_log import *
from app.tracking_module.models.sleep_log import *
from app.tracking_module.models.hydration_log import *
from app.tracking_module.models.weight_log import *

try:
    with engine.connect() as conn:
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        conn.commit()
    print('[init] pgvector extension ready.')
except Exception as e:
    print(f'[init] pgvector not available (non-fatal): {e}')

Base.metadata.create_all(bind=engine)
print('[init] All tables created.')
"
echo "[init] Done."

# ── Step 1: PostgreSQL seed ────────────────────────────────────────────────
echo ""
echo "[seed] Checking database state..."

if [ "$RESEED_DB" = "true" ]; then
    echo "[seed] RESEED_DB=true — clearing and re-seeding all data..."
    python -m scripts.seed --clear

else
    # Count existing foods to decide whether to seed
    FOOD_COUNT=$(python -c "
from dotenv import load_dotenv; load_dotenv()
from app.db.database import engine
from sqlalchemy import text
try:
    with engine.connect() as c:
        print(c.execute(text('SELECT COUNT(*) FROM central_foods')).scalar())
except Exception:
    print(0)
" 2>/dev/null || echo "0")

    if [ "$FOOD_COUNT" = "0" ]; then
        echo "[seed] Tables are empty — running full seed (foods + exercises + embeddings)..."
        echo "[seed] This takes 2-5 minutes on first run."
        python -m scripts.seed
    else
        echo "[seed] Found $FOOD_COUNT foods — filling any missing embeddings only..."
        python -m scripts.seed --embed-only
    fi
fi

echo "[seed] Done."

# ── Step 2: ChromaDB vector database ──────────────────────────────────────
echo ""
echo "[vector-db] Checking ChromaDB state..."

CHROMA_PATH="app/ai_services/ai_coach/chroma_db"
RESOURCES_CSV="merged_resources.csv"
HASH_FILE="data/scraped_resources/resources_hash.txt"

if [ "$REBUILD_VECTOR_DB" = "true" ]; then
    # Manual override — honour SCRAPE_RESOURCES flag
    if [ "$SCRAPE_RESOURCES" = "true" ]; then
        echo "[vector-db] REBUILD_VECTOR_DB+SCRAPE_RESOURCES=true — re-scraping and rebuilding..."
        python -m scripts.init_vector_db --scrape --force-rebuild
    else
        echo "[vector-db] REBUILD_VECTOR_DB=true — rebuilding from existing scraped data..."
        python -m scripts.init_vector_db --force-rebuild
    fi

else
    # Auto-detect CSV changes via MD5 hash
    CURRENT_HASH=""
    if [ -f "$RESOURCES_CSV" ]; then
        CURRENT_HASH=$(md5sum "$RESOURCES_CSV" | cut -d' ' -f1)
    fi

    STORED_HASH=""
    if [ -f "$HASH_FILE" ]; then
        STORED_HASH=$(cat "$HASH_FILE")
    fi

    if [ -n "$CURRENT_HASH" ] && [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
        echo "[vector-db] merged_resources.csv has changed (hash: $CURRENT_HASH)."
        echo "[vector-db] Auto-triggering re-scrape + rebuild..."
        python -m scripts.init_vector_db --scrape --force-rebuild

    elif [ ! -d "$CHROMA_PATH" ]; then
        echo "[vector-db] ChromaDB not found — building for the first time..."
        echo "[vector-db] This takes 1-3 minutes on first run."
        python -m scripts.init_vector_db

    else
        echo "[vector-db] ChromaDB is up to date — skipping."
        echo "[vector-db] Edit merged_resources.csv or set REBUILD_VECTOR_DB=true to rebuild."
    fi
fi

echo "[vector-db] Done."

# ── Start application ──────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo "  Initialization complete — starting API"
echo "======================================================"
echo ""

exec "$@"
