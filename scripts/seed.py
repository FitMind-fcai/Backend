"""
Full database seed — imports foods + exercises then generates embeddings in one run.

Usage (run from repo root inside the API container):
    python -m scripts.seed                   # import + embed everything
    python -m scripts.seed --clear           # wipe tables first, then import + embed
    python -m scripts.seed --embed-only      # skip import, just fill missing embeddings

Steps:
  1. Import nutrition.csv        → central_foods
  2. Import megaGymDataset.csv   → central_exercises
  3. Generate embeddings for all rows that still have name_embedding = NULL
  4. Build IVFFlat indexes for fast similarity search
"""

import argparse
import csv
import logging
import re
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, func as sql_func, text
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

BATCH_SIZE = 256
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

ROOT = Path(__file__).parent.parent
FOOD_CSV = ROOT / "nutrition.csv"
ARABIC_FOOD_CSV = ROOT / "data" / "arabic_foods_nutrition.csv"
EXERCISE_CSV = ROOT / "megaGymDataset.csv"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _extract_float(val) -> Optional[float]:
    if not val or str(val).strip() == "":
        return None
    m = re.search(r"[-+]?\d*\.\d+|\d+", str(val))
    return float(m.group(0)) if m else None


def _vec_str(vec) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


# ──────────────────────────────────────────────────────────────────────────────
# Step 1 — Import foods
# ──────────────────────────────────────────────────────────────────────────────

def _transform_food(row: dict) -> Optional[dict]:
    name_raw = row.get("name", "").strip()
    if not name_raw:
        return None

    parts = [p.strip() for p in name_raw.split(",")]
    name = parts[0] if len(parts) == 1 else f"{parts[0]} ({', '.join(parts[1:])})"

    calories = _extract_float(row.get("calories"))
    protein  = _extract_float(row.get("protein"))
    carbs    = _extract_float(row.get("carbohydrate"))
    fats     = _extract_float(row.get("fat"))
    if any(v is None for v in (calories, protein, carbs, fats)):
        return None

    serving_str = row.get("serving_size", "100 g")
    serving_g   = _extract_float(serving_str) or 100.0

    return {
        "food_name":        name,
        "food_category":    None,
        "calories_per_100g": calories,
        "protein_per_100g":  protein,
        "carbs_per_100g":    carbs,
        "fats_per_100g":     fats,
        "fiber_per_100g":    _extract_float(row.get("fiber")),
        "serving_size_g":    serving_g,
        "serving_description": serving_str,
        "dietary_tags":     [],
        "source":           "nutrition.csv",
        "is_active":        True,
    }


def import_foods(db: Session, clear: bool):
    from app.planning_module.models.plan import CentralFood

    if clear:
        log.info("Clearing central_foods …")
        db.query(CentralFood).delete()
        db.commit()

    log.info("Reading %s …", FOOD_CSV)
    records = []
    with open(FOOD_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            r = _transform_food(row)
            if r:
                records.append(r)
    log.info("  %d valid food rows", len(records))

    inserted = updated = 0
    for i, data in enumerate(records):
        existing = db.query(CentralFood).filter(
            sql_func.lower(CentralFood.food_name) == data["food_name"].lower()
        ).first()
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(CentralFood(**data))
            inserted += 1

        if (i + 1) % BATCH_SIZE == 0:
            db.commit()
            log.info("  foods … %d / %d", i + 1, len(records))

    db.commit()
    log.info("Foods done — inserted: %d  updated: %d", inserted, updated)


# ──────────────────────────────────────────────────────────────────────────────
# Step 1b — Import Arabic foods
# ──────────────────────────────────────────────────────────────────────────────

def _transform_arabic_food(row: dict) -> Optional[dict]:
    name = row.get("food_name", "").strip()
    if not name:
        return None

    calories = _extract_float(row.get("calories_per_100g"))
    protein  = _extract_float(row.get("protein_per_100g"))
    carbs    = _extract_float(row.get("carbs_per_100g"))
    fats     = _extract_float(row.get("fats_per_100g"))
    if any(v is None for v in (calories, protein, carbs, fats)):
        return None
    if calories == 0 and protein == 0 and carbs == 0 and fats == 0:
        return None

    import json
    tags_raw = row.get("dietary_tags", "[]")
    try:
        tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw
    except (json.JSONDecodeError, TypeError):
        tags = []

    name_ar = row.get("food_name_ar", "").strip()
    serving_desc = row.get("serving_description", "100 g").strip()
    serving_g = _extract_float(row.get("serving_size_g")) or 100.0

    return {
        "food_name":         name,
        "food_name_ar":      name_ar if name_ar and name_ar != "nan" else None,
        "food_category":     row.get("food_category", "").strip() or None,
        "calories_per_100g": calories,
        "protein_per_100g":  protein,
        "carbs_per_100g":    carbs,
        "fats_per_100g":     fats,
        "fiber_per_100g":    _extract_float(row.get("fiber_per_100g")),
        "serving_size_g":    serving_g,
        "serving_description": serving_desc,
        "dietary_tags":      tags,
        "source":            row.get("source", "kaggle-egyptian-foods").strip(),
        "is_active":         True,
    }


def import_arabic_foods(db: Session):
    from app.planning_module.models.plan import CentralFood

    if not ARABIC_FOOD_CSV.exists():
        log.info("No Arabic foods CSV found at %s — skipping", ARABIC_FOOD_CSV)
        return

    log.info("Reading %s …", ARABIC_FOOD_CSV)
    records = []
    with open(ARABIC_FOOD_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            r = _transform_arabic_food(row)
            if r:
                records.append(r)
    log.info("  %d valid Arabic food rows", len(records))

    inserted = updated = 0
    for i, data in enumerate(records):
        existing = db.query(CentralFood).filter(
            sql_func.lower(CentralFood.food_name) == data["food_name"].lower()
        ).first()
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(CentralFood(**data))
            inserted += 1

        if (i + 1) % BATCH_SIZE == 0:
            db.commit()
            log.info("  Arabic foods … %d / %d", i + 1, len(records))

    db.commit()
    log.info("Arabic foods done — inserted: %d  updated: %d", inserted, updated)


# ──────────────────────────────────────────────────────────────────────────────
# Step 2 — Import exercises
# ──────────────────────────────────────────────────────────────────────────────

def _transform_exercise(row: dict) -> Optional[dict]:
    name = row.get("Title", "").strip()
    if not name:
        return None
    equipment = row.get("Equipment", "").strip()
    if not equipment or equipment.lower() == "none":
        equipment = "Body Only"
    return {
        "name":                name,
        "exercise_type":       row.get("Type", "Strength").strip() or "Strength",
        "primary_muscle_group": row.get("BodyPart", "Full Body").strip() or "Full Body",
        "secondary_muscles":   None,
        "equipment_required":  equipment,
        "difficulty_level":    row.get("Level", "Beginner").strip() or "Beginner",
        "location":            "Any",
        "instructions":        row.get("Desc", "").strip() or None,
        "video_url":           None,
        "image_url":           None,
        "is_active":           True,
    }


def import_exercises(db: Session, clear: bool):
    from app.planning_module.models.plan import CentralExercise

    if clear:
        log.info("Clearing central_exercises …")
        db.query(CentralExercise).delete()
        db.commit()

    log.info("Reading %s …", EXERCISE_CSV)
    seen: dict[str, dict] = {}
    with open(EXERCISE_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            r = _transform_exercise(row)
            if r and r["name"].lower() not in seen:
                seen[r["name"].lower()] = r
    records = list(seen.values())
    log.info("  %d unique exercise rows", len(records))

    inserted = updated = 0
    for i, data in enumerate(records):
        existing = db.query(CentralExercise).filter(
            sql_func.lower(CentralExercise.name) == data["name"].lower()
        ).first()
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(CentralExercise(**data))
            inserted += 1

        if (i + 1) % BATCH_SIZE == 0:
            db.commit()
            log.info("  exercises … %d / %d", i + 1, len(records))

    db.commit()
    log.info("Exercises done — inserted: %d  updated: %d", inserted, updated)


# ──────────────────────────────────────────────────────────────────────────────
# Step 3 — Generate embeddings
# ──────────────────────────────────────────────────────────────────────────────

def generate_embeddings(engine, model):
    # Fetch the list of rows needing embeddings (short-lived connection)
    with engine.connect() as conn:
        food_rows = conn.execute(
            text("SELECT id, food_name FROM central_foods WHERE is_active = true AND name_embedding IS NULL ORDER BY id")
        ).fetchall()
        conn.commit()
    log.info("%d foods need embeddings", len(food_rows))

    for start in range(0, len(food_rows), BATCH_SIZE):
        batch = food_rows[start: start + BATCH_SIZE]
        vecs  = model.encode([r.food_name for r in batch], normalize_embeddings=True, show_progress_bar=False)
        with engine.connect() as conn:
            for row, vec in zip(batch, vecs):
                conn.execute(
                    text("UPDATE central_foods SET name_embedding = CAST(:vec AS vector) WHERE id = :id"),
                    {"vec": _vec_str(vec), "id": row.id},
                )
            conn.commit()
        log.info("  food embeddings … %d / %d", min(start + BATCH_SIZE, len(food_rows)), len(food_rows))

    with engine.connect() as conn:
        exercise_rows = conn.execute(
            text("SELECT id, name FROM central_exercises WHERE is_active = true AND name_embedding IS NULL ORDER BY id")
        ).fetchall()
        conn.commit()
    log.info("%d exercises need embeddings", len(exercise_rows))

    for start in range(0, len(exercise_rows), BATCH_SIZE):
        batch = exercise_rows[start: start + BATCH_SIZE]
        vecs  = model.encode([r.name for r in batch], normalize_embeddings=True, show_progress_bar=False)
        with engine.connect() as conn:
            for row, vec in zip(batch, vecs):
                conn.execute(
                    text("UPDATE central_exercises SET name_embedding = CAST(:vec AS vector) WHERE id = :id"),
                    {"vec": _vec_str(vec), "id": row.id},
                )
            conn.commit()
        log.info("  exercise embeddings … %d / %d", min(start + BATCH_SIZE, len(exercise_rows)), len(exercise_rows))

    # ── IVFFlat indexes ────────────────────────────────────────────────
    for ddl in [
        "CREATE INDEX IF NOT EXISTS idx_central_foods_name_embedding "
        "ON central_foods USING ivfflat (name_embedding vector_cosine_ops) WITH (lists = 100)",
        "CREATE INDEX IF NOT EXISTS idx_central_exercises_name_embedding "
        "ON central_exercises USING ivfflat (name_embedding vector_cosine_ops) WITH (lists = 100)",
    ]:
        try:
            with engine.connect() as conn:
                conn.execute(text(ddl))
                conn.commit()
        except Exception as exc:
            log.warning("Index skipped (need more rows for IVFFlat): %s", exc)

    log.info("Embeddings done.")


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Seed the FitMind database")
    parser.add_argument("--clear",      action="store_true", help="Wipe tables before importing")
    parser.add_argument("--embed-only", action="store_true", help="Skip CSV import, only fill missing embeddings")
    args = parser.parse_args()

    import os
    from app.db.database import SessionLocal, engine
    from app.planning_module.models.plan import CentralFood, CentralExercise  # noqa: F401 — register models
    from app.auth_module.models.user import User                               # noqa: F401 — FK target

    if not args.embed_only:
        db: Session = SessionLocal()
        try:
            import_foods(db, clear=args.clear)
            import_arabic_foods(db)
            import_exercises(db, clear=args.clear)
        finally:
            db.close()

    log.info("Loading embedding model %s …", EMBEDDING_MODEL)
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBEDDING_MODEL)

    generate_embeddings(engine, model)
    log.info("All done.")


if __name__ == "__main__":
    main()
