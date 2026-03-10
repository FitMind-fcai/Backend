"""
Import USDA FoodData Central (Foundation Foods) into the central_foods table.

Usage:
    python scripts/import_usda_foods.py                    # dry-run (preview only)
    python scripts/import_usda_foods.py --import           # actual DB import
    python scripts/import_usda_foods.py --import --clear   # clear table first, then import

Dataset: FoodData_Central_foundation_food_json_2025-04-24.json
  - 340 foundation food items (raw/minimally processed ingredients)
  - All nutrient values stored per 100g (USDA standard)
  - serving_size_g + serving_description stored for per-serving display
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Optional

# Allow importing app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# ──────────────────────────────────────────────────────────────────────────────
# Dietary tags inferred from USDA food category
# ──────────────────────────────────────────────────────────────────────────────

CATEGORY_DIETARY_TAGS: dict[str, list[str]] = {
    "Fruits and Fruit Juices":           ["vegan", "vegetarian", "gluten-free"],
    "Vegetables and Vegetable Products": ["vegan", "vegetarian", "gluten-free"],
    "Legumes and Legume Products":       ["vegan", "vegetarian", "high-fiber"],
    "Nut and Seed Products":             ["vegan", "vegetarian", "gluten-free", "high-fat"],
    "Dairy and Egg Products":            ["vegetarian", "high-protein"],
    "Beef Products":                     ["high-protein", "gluten-free"],
    "Poultry Products":                  ["high-protein", "gluten-free", "low-fat"],
    "Pork Products":                     ["high-protein", "gluten-free"],
    "Finfish and Shellfish Products":    ["high-protein", "gluten-free", "low-fat"],
    "Lamb, Veal, and Game Products":     ["high-protein", "gluten-free"],
    "Sausages and Luncheon Meats":       ["high-protein"],
    "Cereal Grains and Pasta":           ["vegetarian", "high-carb"],
    "Baked Products":                    ["vegetarian"],
    "Sweets":                            ["vegetarian"],
    "Fats and Oils":                     ["vegan", "gluten-free"],
    "Beverages":                         ["vegan", "gluten-free"],
    "Soups, Sauces, and Gravies":        [],
    "Spices and Herbs":                  ["vegan", "vegetarian", "gluten-free"],
    "Restaurant Foods":                  [],
}


# ──────────────────────────────────────────────────────────────────────────────
# Nutrient extraction helpers
# ──────────────────────────────────────────────────────────────────────────────

NUTRIENT_MAP = {
    "energy":  ["Energy"],
    "protein": ["Protein"],
    "carbs":   ["Carbohydrate, by difference"],
    "fat":     ["Total lipid (fat)"],
    "fiber":   ["Fiber, total dietary"],
}


def extract_nutrients(food_nutrients: list) -> dict:
    """Return per-100g macro dict from a food's nutrient list."""
    result = {k: None for k in NUTRIENT_MAP}
    for entry in food_nutrients:
        nutrient_name = entry.get("nutrient", {}).get("name", "")
        amount = entry.get("amount")
        if amount is None:
            continue
        for key, names in NUTRIENT_MAP.items():
            if result[key] is None and nutrient_name in names:
                result[key] = float(amount)
    return result


def get_serving(food_portions: list) -> tuple[float, str]:
    """
    Return (gram_weight, serving_label) for the first meaningful portion.
    Falls back to 100g if no portions are defined.
    """
    if not food_portions:
        return 100.0, "100g"

    portion = food_portions[0]
    gram_weight = portion.get("gramWeight") or 100.0
    amount = portion.get("amount", 1)
    unit = portion.get("measureUnit", {}).get("abbreviation") or \
           portion.get("measureUnit", {}).get("name") or "serving"
    modifier = portion.get("modifier") or ""

    label_parts = []
    if amount and amount != 1:
        label_parts.append(str(int(amount) if float(amount).is_integer() else amount))
    label_parts.append(unit)
    if modifier:
        label_parts.append(modifier)
    label_parts.append(f"({round(gram_weight)}g)")

    return float(gram_weight), " ".join(label_parts)


# ──────────────────────────────────────────────────────────────────────────────
# Transform a single USDA food entry → CentralFood dict
# ──────────────────────────────────────────────────────────────────────────────

def transform(food: dict) -> Optional[dict]:
    """
    Convert a USDA FoundationFood entry to a CentralFood-compatible dict.
    Macros stored per 100g. Returns None if required macros are missing.
    """
    nutrients = extract_nutrients(food.get("foodNutrients", []))

    # Skip entries missing any required macro
    if any(nutrients[k] is None for k in ("energy", "protein", "carbs", "fat")):
        return None

    gram_weight, serving_label = get_serving(food.get("foodPortions", []))
    category = food.get("foodCategory", {}).get("description", "")

    return {
        "food_name":           food["description"],
        "food_category":       category or None,
        "calories_per_100g":   round(nutrients["energy"], 2),
        "protein_per_100g":    round(nutrients["protein"], 2),
        "carbs_per_100g":      round(nutrients["carbs"], 2),
        "fats_per_100g":       round(nutrients["fat"], 2),
        "fiber_per_100g":      round(nutrients["fiber"], 2) if nutrients["fiber"] is not None else None,
        "serving_size_g":      gram_weight,
        "serving_description": serving_label,
        "dietary_tags":        CATEGORY_DIETARY_TAGS.get(category, []),
        "usda_fdc_id":         food.get("fdcId"),
        "source":              "USDA",
        "is_active":           True,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def load_and_transform(json_path: Path) -> list[dict]:
    print(f"Loading {json_path} ...")
    with open(json_path) as f:
        data = json.load(f)

    foods = data.get("FoundationFoods", [])
    print(f"  Found {len(foods)} foundation food entries")

    records, skipped = [], []
    for food in foods:
        record = transform(food)
        if record:
            records.append(record)
        else:
            skipped.append(food.get("description", "unknown"))

    print(f"  Transformed: {len(records)}  |  Skipped (missing macros): {len(skipped)}")
    if skipped:
        print(f"  Skipped: {', '.join(skipped[:10])}" + (" ..." if len(skipped) > 10 else ""))
    return records


def preview(records: list[dict]):
    print("\n" + "=" * 70)
    print("DRY RUN PREVIEW — first 5 records")
    print("=" * 70)
    for r in records[:5]:
        serving_kcal = round(r["calories_per_100g"] * r["serving_size_g"] / 100)
        print(f"\n  food_name    : {r['food_name']}")
        print(f"  category     : {r['food_category']}")
        print(f"  per 100g     : {r['calories_per_100g']} kcal | P:{r['protein_per_100g']}g C:{r['carbs_per_100g']}g F:{r['fats_per_100g']}g")
        print(f"  serving      : {r['serving_description']} → ~{serving_kcal} kcal")
        print(f"  dietary_tags : {r['dietary_tags']}")
        print(f"  usda_fdc_id  : {r['usda_fdc_id']}")
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
            # Upsert: prefer USDA FDC ID, fall back to name match
            existing = None
            if data.get("usda_fdc_id"):
                existing = db.query(CentralFood).filter(
                    CentralFood.usda_fdc_id == data["usda_fdc_id"]
                ).first()
            if not existing:
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
                print(f"  ... {i + 1}/{len(records)}")

        db.commit()
        print(f"\n✅ Done — inserted: {inserted}  updated: {updated}")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Import failed: {e}")
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Import USDA Foundation Foods into central_foods")
    parser.add_argument("--import", dest="do_import", action="store_true",
                        help="Write records to the database (default: dry-run preview)")
    parser.add_argument("--clear", action="store_true",
                        help="Delete all existing rows in central_foods before importing")
    args = parser.parse_args()
    """
    Return (gram_weight, serving_label) for the first meaningful portion.
    Falls back to 100g if no portions are defined.
    """
    if not food_portions:
        return 100.0, "100g"

    portion = food_portions[0]
    gram_weight = portion.get("gramWeight") or 100.0
    amount = portion.get("amount", 1)
    unit = portion.get("measureUnit", {}).get("abbreviation") or \
           portion.get("measureUnit", {}).get("name") or "serving"
    modifier = portion.get("modifier") or ""

    label_parts = []
    if amount and amount != 1:
        label_parts.append(str(int(amount) if float(amount).is_integer() else amount))
    label_parts.append(unit)
    if modifier:
        label_parts.append(modifier)
    label_parts.append(f"({round(gram_weight)}g)")

    return float(gram_weight), " ".join(label_parts)


    json_path = Path(__file__).parent.parent / "FoodData_Central_foundation_food_json_2025-04-24.json"
    if not json_path.exists():
        print(f"❌ File not found: {json_path}")
        sys.exit(1)

    records = load_and_transform(json_path)

    if not args.do_import:
        preview(records)
    else:
        run_import(records, clear=args.clear)


if __name__ == "__main__":
    main()
