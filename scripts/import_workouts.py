"""
Import workouts from megaGymDataset.csv into the central_exercises table.

Usage:
    python scripts/import_workouts.py                    # dry-run (preview only)
    python scripts/import_workouts.py --import           # actual DB import
    python scripts/import_workouts.py --import --clear   # clear table first, then import
"""

import sys
import csv
import argparse
from pathlib import Path
from typing import Optional

# Allow importing app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

def pd_isna(val):
    return val is None or str(val).strip() == ""

def transform(row: dict) -> Optional[dict]:
    name_raw = row.get("Title", "").strip()
    if not name_raw:
        return None

    # Skip exercises with missing essential data
    if pd_isna(row.get("Desc")) and pd_isna(row.get("BodyPart")):
        return None

    equipment = row.get("Equipment", "Bodyweight").strip()
    if pd_isna(equipment) or equipment.lower() == "none":
        equipment = "Body Only"

    return {
        "name": name_raw,
        "exercise_type": row.get("Type", "Strength").strip() or "Strength",
        "primary_muscle_group": row.get("BodyPart", "Full Body").strip() or "Full Body",
        "secondary_muscles": None,
        "equipment_required": equipment,
        "difficulty_level": row.get("Level", "Beginner").strip() or "Beginner",
        "location": "Any",
        "instructions": row.get("Desc", "").strip() or None,
        "video_url": None,
        "image_url": None,
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
                skipped.append(row.get("Title", "unknown"))

    print(f"  Transformed: {len(records)}  |  Skipped: {len(skipped)}")
    return records

def preview(records: list[dict]):
    print("\n" + "=" * 70)
    print("DRY RUN PREVIEW — first 5 records")
    print("=" * 70)
    for r in records[:5]:
        print(f"\n  name         : {r['name']}")
        print(f"  type         : {r['exercise_type']} | muscle: {r['primary_muscle_group']}")
        print(f"  equipment    : {r['equipment_required']} | level: {r['difficulty_level']}")
        desc = r['instructions'] or ""
        print(f"  instructions : {desc[:60]}..." if len(desc) > 60 else f"  instructions : {desc}")
    print("\nRun with --import to write to the database.")

def run_import(records: list[dict], clear: bool):
    from app.db.database import SessionLocal
    from app.planning_module.models.plan import CentralExercise
    from app.auth_module.models.user import User  # noqa: F401 - ensure users table is registered for FK resolution
    from sqlalchemy.orm import Session
    from sqlalchemy import func as sql_func

    db: Session = SessionLocal()
    try:
        if clear:
            print("\nClearing central_exercises table ...")
            db.query(CentralExercise).delete()
            db.commit()
            print("  Table cleared.")

        print(f"\nImporting {len(records)} records ...")
        inserted = updated = 0
        batch_size = 50

        # Create a dictionary to avoid duplicate names in the dataset itself
        # We will keep the first occurrence
        unique_records = {}
        for data in records:
            name_key = data["name"].lower()
            if name_key not in unique_records:
                unique_records[name_key] = data

        unique_list = list(unique_records.values())

        for i, data in enumerate(unique_list):
            existing = db.query(CentralExercise).filter(
                sql_func.lower(CentralExercise.name) == data["name"].lower()
            ).first()

            if existing:
                for key, value in data.items():
                    setattr(existing, key, value)
                updated += 1
            else:
                db.add(CentralExercise(**data))
                inserted += 1

            if (i + 1) % batch_size == 0:
                db.commit()
                sys.stdout.write(f"\r  ... {i + 1}/{len(unique_list)}")
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
    parser = argparse.ArgumentParser(description="Import workouts from megaGymDataset.csv")
    parser.add_argument("--import", dest="do_import", action="store_true",
                        help="Write records to the database (default: dry-run preview)")
    parser.add_argument("--clear", action="store_true",
                        help="Delete all existing rows in central_exercises before importing")
    args = parser.parse_args()

    csv_path = Path(__file__).parent.parent / "megaGymDataset.csv"
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
