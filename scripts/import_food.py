"""
Import foods from nutrition.csv into the central_foods table.

Usage:
    python scripts/import_food.py                    # dry-run (preview only)
    python scripts/import_food.py --import           # actual DB import
    python scripts/import_food.py --import --clear   # clear table first, then import
"""

import sys
import csv
import argparse
import re
from pathlib import Path
from typing import Optional

# Allow importing app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

def extract_float(value_str: str) -> Optional[float]:
    """Extract float from a string like '0.1g', '100 g', '381', ''"""
    if not value_str or pd_isna(value_str):
        return None
    match = re.search(r"[-+]?\d*\.\d+|\d+", str(value_str))
    if match:
        return float(match.group(0))
    return None

def pd_isna(val):
    return val is None or str(val).strip() == ""

def clean_food_name(desc: str) -> str:
    """Format descriptions from 'Nuts, pecans' to 'Nuts (pecans)'."""
    parts = [p.strip() for p in desc.split(",")]
    if len(parts) == 1:
        return parts[0]
    
    base = parts[0]
    modifiers = ", ".join(parts[1:])
    return f"{base} ({modifiers})"

def transform(row: dict) -> Optional[dict]:
    name_raw = row.get("name", "").strip()
    if not name_raw:
        return None
    name = clean_food_name(name_raw)

    # Parse nutrients (removing 'g', 'mg' etc. using extract_float)
    calories = extract_float(row.get("calories"))
    protein = extract_float(row.get("protein"))
    carbs = extract_float(row.get("carbohydrate"))
    fats = extract_float(row.get("fat"))
    fiber = extract_float(row.get("fiber"))

    # Skip if required macros are missing
    if any(v is None for v in (calories, protein, carbs, fats)):
        return None

    serving_str = row.get("serving_size", "100 g")
    serving_g = extract_float(serving_str) or 100.0

    return {
        "food_name": name,
        "food_category": None,  # CSV doesn't have a broad category
        "calories_per_100g": calories,
        "protein_per_100g": protein,
        "carbs_per_100g": carbs,
        "fats_per_100g": fats,
        "fiber_per_100g": fiber,
        "serving_size_g": serving_g,
        "serving_description": serving_str,
        "dietary_tags": [], # we don't have enough category info to build these out of the box
        "usda_fdc_id": None,
        "source": "nutrition.csv",
        "is_active": True,
    }

def load_and_transform(csv_path: Path) -> list[dict]:
    print(f"Loading {csv_path} ...")
    records = []
    skipped = []
    
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            record = transform(row)
            if record:
                records.append(record)
            else:
                skipped.append(row.get("name", "unknown"))

    print(f"  Transformed: {len(records)}  |  Skipped: {len(skipped)}")
    return records

def preview(records: list[dict]):
    print("\n" + "=" * 70)
    print("DRY RUN PREVIEW — first 5 records")
    print("=" * 70)
    for r in records[:5]:
        print(f"\n  food_name    : {r['food_name']}")
        print(f"  per 100g     : {r['calories_per_100g']} kcal | P:{r['protein_per_100g']}g C:{r['carbs_per_100g']}g F:{r['fats_per_100g']}g")
        print(f"  serving      : {r['serving_size_g']}g")
    print("\nRun with --import to write to the database.")

def run_import(records: list[dict], clear: bool):
    from app.db.database import SessionLocal
    from app.planning_module.models.plan import CentralFood
    from sqlalchemy.orm import Session
    from sqlalchemy import func as sql_func

    db: Session = SessionLocal()
    try:
        if clear:
            print("\nClearing central_foods table ...")
            db.query(CentralFood).delete()
            db.commit()
            print("  Table cleared.")

        print(f"\nImporting {len(records)} records ...")
        inserted = updated = 0
        batch_size = 50

        for i, data in enumerate(records):
            existing = db.query(CentralFood).filter(
                sql_func.lower(CentralFood.food_name) == data["food_name"].lower()
            ).first()

            if existing:
                for key, value in data.items():
                    setattr(existing, key, value)
                updated += 1
            else:
                db.add(CentralFood(**data))
                inserted += 1

            if (i + 1) % batch_size == 0:
                db.commit()
                sys.stdout.write(f"\r  ... {i + 1}/{len(records)}")
                sys.stdout.flush()

        db.commit()
        print(f"\n✅ Done — inserted: {inserted}  updated: {updated}")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Import failed: {e}")
        raise
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser(description="Import foods from nutrition.csv")
    parser.add_argument("--import", dest="do_import", action="store_true",
                        help="Write records to the database (default: dry-run preview)")
    parser.add_argument("--clear", action="store_true",
                        help="Delete all existing rows in central_foods before importing")
    args = parser.parse_args()

    csv_path = Path(__file__).parent.parent / "nutrition.csv"
    if not csv_path.exists():
        print(f"❌ File not found: {csv_path}")
        sys.exit(1)

    records = load_and_transform(csv_path)

    if not args.do_import:
        preview(records)
    else:
        run_import(records, clear=args.clear)


if __name__ == "__main__":
    main()
