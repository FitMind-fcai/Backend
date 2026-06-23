"""
Download the Egyptian Food & Drinks dataset from Kaggle, enrich each food
with per-100g nutritional estimates via Groq LLM (llama-3.3-70b), and
write a CSV ready for import into central_foods.

Supports resuming: checks how many rows already exist in the output CSV
and continues from there.

Usage:
    pip install kagglehub pandas
    GROQ_API_KEY=gsk_... python -m scripts.generate_arabic_food_nutrition

    # Resume (just run again — it picks up where the output CSV left off):
    GROQ_API_KEY=gsk_... python -m scripts.generate_arabic_food_nutrition

    # Use a local CSV instead of downloading from Kaggle:
    GROQ_API_KEY=gsk_... python -m scripts.generate_arabic_food_nutrition --local-csv path/to/file.csv

Output:  data/arabic_foods_nutrition.csv
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
RAW_CSV = ROOT / "data" / "arabic_foods_raw.csv"
OUTPUT_CSV = ROOT / "data" / "arabic_foods_nutrition.csv"

GROQ_MODEL = "llama-3.3-70b-versatile"
BATCH_SIZE = 15
REQUEST_DELAY = 14

CSV_COLUMNS = [
    "food_name", "food_name_ar", "food_category", "ingredients_en",
    "calories_per_100g", "protein_per_100g", "carbs_per_100g",
    "fats_per_100g", "fiber_per_100g",
    "serving_size_g", "serving_description", "dietary_tags", "source",
]


# ---------------------------------------------------------------------------
# Step 1 — Download dataset once
# ---------------------------------------------------------------------------

def ensure_raw_csv(local_csv: str | None) -> Path:
    if local_csv:
        src = Path(local_csv)
        if not src.exists():
            log.error("File not found: %s", src)
            sys.exit(1)
        return src

    if RAW_CSV.exists():
        log.info("Raw dataset already downloaded: %s", RAW_CSV)
        return RAW_CSV

    import kagglehub
    import pandas as pd

    log.info("Downloading dataset from Kaggle …")
    dataset_path = kagglehub.dataset_download(
        "mohanedmaged/egyptian-food-and-drinks-arabic-and-english",
    )
    csv_files = list(Path(dataset_path).rglob("*.csv"))
    if not csv_files:
        log.error("No CSV files found in downloaded dataset at %s", dataset_path)
        sys.exit(1)
    src_csv = csv_files[0]
    log.info("Found dataset CSV: %s", src_csv)

    df = pd.read_csv(src_csv)
    log.info("Loaded %d rows, columns: %s", len(df), list(df.columns))

    RAW_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(RAW_CSV, index=False, encoding="utf-8")
    log.info("Saved raw dataset to %s", RAW_CSV)
    return RAW_CSV


# ---------------------------------------------------------------------------
# Step 2 — Parse raw CSV into a clean food list
# ---------------------------------------------------------------------------

def load_foods(csv_path: Path) -> list[dict]:
    import pandas as pd
    df = pd.read_csv(csv_path)

    name_en_col = next((c for c in df.columns if "name_en" in c.lower()), None)
    name_ar_col = next((c for c in df.columns if "name_ar" in c.lower()), None)
    ing_en_col = next((c for c in df.columns if "ingredients_en" in c.lower()), None)
    cat_en_col = next((c for c in df.columns if "category_en" in c.lower() or "main_category_en" in c.lower()), None)

    if not name_en_col:
        log.error("Cannot find English name column. Available: %s", list(df.columns))
        sys.exit(1)

    log.info("Columns mapped: name_en=%s, name_ar=%s, ing_en=%s, cat_en=%s",
             name_en_col, name_ar_col, ing_en_col, cat_en_col)

    foods = []
    seen = set()
    for _, row in df.iterrows():
        name_en = str(row.get(name_en_col, "")).strip()
        if not name_en or name_en.lower() == "nan":
            continue
        key = name_en.lower()
        if key in seen:
            continue
        seen.add(key)

        name_ar = str(row.get(name_ar_col, "")).strip() if name_ar_col else ""
        ingredients = str(row.get(ing_en_col, "")).strip() if ing_en_col else ""
        category = str(row.get(cat_en_col, "")).strip() if cat_en_col else ""

        foods.append({
            "name_en": name_en,
            "name_ar": name_ar if name_ar != "nan" else "",
            "ingredients_en": ingredients if ingredients != "nan" else "",
            "category": category if category != "nan" else "",
        })

    log.info("Unique foods: %d", len(foods))
    return foods


# ---------------------------------------------------------------------------
# Step 3 — Groq LLM calls
# ---------------------------------------------------------------------------

def groq_request(api_key: str, messages: list, temperature: float = 0.1) -> str:
    body = json.dumps({
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4096,
    }).encode()

    req = Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "FitMind/1.0",
        },
        method="POST",
    )

    for attempt in range(4):
        try:
            with urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode())
                return data["choices"][0]["message"]["content"]
        except HTTPError as e:
            if e.code == 429:
                wait = (2 ** attempt) * 5
                log.warning("Rate limited (429), waiting %ds …", wait)
                time.sleep(wait)
                continue
            if e.code == 413:
                log.error("Request too large (413) — reduce BATCH_SIZE")
                raise
            raise
        except Exception as e:
            if attempt < 3:
                wait = (2 ** attempt) * 3
                log.warning("Request failed (%s), retrying in %ds …", e, wait)
                time.sleep(wait)
                continue
            raise

    raise RuntimeError("Groq API failed after 4 attempts")


def estimate_batch(foods: list[dict], api_key: str) -> list[dict]:
    food_list = "\n".join(
        f'{i+1}. "{f["name_en"]}" (Ingredients: {f["ingredients_en"]})'
        for i, f in enumerate(foods)
    )

    prompt = f"""Estimate the nutritional values PER 100 GRAMS for each of these Egyptian/Middle Eastern foods.
Base your estimates on the ingredients provided and standard food composition data (USDA, FAO).

Foods:
{food_list}

Return ONLY a JSON array (no markdown fences, no text before/after). Each element:
{{"index":<1-based>,"calories":float,"protein":float,"carbs":float,"fat":float,"fiber":float,"serving_g":float,"serving_desc":"string"}}

serving_g = typical single serving weight in grams.
serving_desc = e.g. "1 bowl", "2 pieces", "1 sandwich".
All nutrition values must be per 100g, NOT per serving."""

    system = (
        "You are a clinical nutritionist specializing in Egyptian and Middle Eastern cuisine. "
        "Provide accurate per-100g nutritional estimates. Use established food composition data. "
        "Return ONLY valid JSON — no markdown code fences, no explanation."
    )

    raw = groq_request(api_key, [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ])

    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        results = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            results = json.loads(match.group(0))
        else:
            log.error("Failed to parse LLM response:\n%s", raw[:500])
            return []

    return results


def derive_dietary_tags(ingredients: str, category: str) -> list[str]:
    tags = []
    ing_lower = (ingredients or "").lower()
    cat_lower = (category or "").lower()

    meat_keywords = [
        "chicken", "beef", "lamb", "meat", "liver", "pigeon",
        "rabbit", "duck", "fish", "shrimp", "seafood", "sausage",
        "لحم", "دجاج", "سمك", "كبد",
    ]
    dairy_keywords = ["milk", "cheese", "cream", "yogurt", "butter", "لبن", "جبن"]
    egg_keywords = ["egg", "بيض"]

    has_meat = any(k in ing_lower for k in meat_keywords)
    has_dairy = any(k in ing_lower for k in dairy_keywords)
    has_egg = any(k in ing_lower for k in egg_keywords)

    if not has_meat and not has_dairy and not has_egg:
        tags.append("vegan")
        tags.append("vegetarian")
    elif not has_meat:
        tags.append("vegetarian")

    if "dessert" in cat_lower or "حلويات" in cat_lower or "sweet" in cat_lower:
        tags.append("dessert")

    return tags


# ---------------------------------------------------------------------------
# Step 4 — Process with resume support
# ---------------------------------------------------------------------------

def count_completed() -> int:
    if not OUTPUT_CSV.exists():
        return 0
    with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        return sum(1 for _ in reader)


def append_rows(rows: list[dict], write_header: bool):
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if write_header else "a"
    with open(OUTPUT_CSV, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def process(foods: list[dict], api_key: str):
    done = count_completed()
    total = len(foods)

    if done >= total:
        log.info("All %d foods already processed!", total)
        return

    is_new = done == 0
    pending = foods[done:]
    log.info("Total: %d | Already done: %d | Remaining: %d", total, done, len(pending))

    total_batches = (len(pending) + BATCH_SIZE - 1) // BATCH_SIZE
    processed_this_run = 0

    for batch_idx in range(0, len(pending), BATCH_SIZE):
        batch = pending[batch_idx: batch_idx + BATCH_SIZE]
        batch_num = batch_idx // BATCH_SIZE + 1
        log.info("Batch %d/%d (%d foods) …", batch_num, total_batches, len(batch))

        try:
            estimates = estimate_batch(batch, api_key)
        except HTTPError as e:
            if e.code == 429:
                log.warning(
                    "Rate limit hit after %d foods this run (%d/%d total). "
                    "Stopping — run again later to continue.",
                    processed_this_run, done + processed_this_run, total,
                )
                return
            log.error("Batch %d failed: %s — stopping to avoid writing zeros", batch_num, e)
            return
        except Exception as e:
            log.error("Batch %d failed: %s — stopping to avoid writing zeros", batch_num, e)
            return

        est_map = {}
        for est in estimates:
            idx = est.get("index", 0) - 1
            if 0 <= idx < len(batch):
                est_map[idx] = est

        rows = []
        for i, food in enumerate(batch):
            est = est_map.get(i, {})
            if not est:
                log.warning("  No estimate for: %s — skipping", food["name_en"])
                continue

            tags = derive_dietary_tags(food["ingredients_en"], food["category"])
            rows.append({
                "food_name": food["name_en"],
                "food_name_ar": food["name_ar"],
                "food_category": food["category"],
                "ingredients_en": food["ingredients_en"],
                "calories_per_100g": round(est.get("calories", 0), 1),
                "protein_per_100g": round(est.get("protein", 0), 1),
                "carbs_per_100g": round(est.get("carbs", 0), 1),
                "fats_per_100g": round(est.get("fat", 0), 1),
                "fiber_per_100g": round(est.get("fiber", 0), 1),
                "serving_size_g": round(est.get("serving_g", 100), 0),
                "serving_description": est.get("serving_desc", "100 g"),
                "dietary_tags": json.dumps(tags),
                "source": "kaggle-egyptian-foods",
            })

        write_header = is_new and batch_idx == 0
        append_rows(rows, write_header)
        processed_this_run += len(batch)
        log.info("  Saved — %d/%d total", done + processed_this_run, total)

        if batch_idx + BATCH_SIZE < len(pending):
            time.sleep(REQUEST_DELAY)

    log.info("This run complete! %d/%d total done.", done + processed_this_run, total)
    if done + processed_this_run >= total:
        log.info("All foods processed! You can now run: python -m scripts.seed")


def main():
    parser = argparse.ArgumentParser(description="Generate Arabic food nutrition CSV")
    parser.add_argument("--api-key", default=None, help="Groq API key (or set GROQ_API_KEY env var)")
    parser.add_argument("--local-csv", default=None, help="Path to a local CSV instead of downloading from Kaggle")
    parser.add_argument("--reset", action="store_true", help="Delete output CSV and start over")
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("GROQ_API_KEY")
    if not api_key:
        log.error("No Groq API key. Pass --api-key or set GROQ_API_KEY env var.")
        sys.exit(1)

    if args.reset:
        for f in [OUTPUT_CSV, RAW_CSV]:
            if f.exists():
                f.unlink()
                log.info("Deleted %s", f)

    raw_path = ensure_raw_csv(args.local_csv)
    foods = load_foods(raw_path)
    process(foods, api_key)


if __name__ == "__main__":
    main()
