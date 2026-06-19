"""
Non-interactive vector DB initializer — designed for Docker / CI use.
Replaces setup_vector_db.py (which requires user input).

Auto-detection
--------------
On every startup entrypoint.sh computes an MD5 of merged_resources.csv and
compares it with the hash stored in data/scraped_resources/resources_hash.txt.
If they differ the script is called with --scrape --force-rebuild automatically
— no manual flag needed after you edit the CSV.

Manual usage
------------
    python -m scripts.init_vector_db                    # build only if chroma_db missing
    python -m scripts.init_vector_db --force-rebuild    # rebuild from existing JSON
    python -m scripts.init_vector_db --scrape           # re-scrape CSV then rebuild
"""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

CHROMA_PATH   = Path("app/ai_services/ai_coach/chroma_db")
SCRAPED_DATA  = Path("data/scraped_resources/scraped_documents.json")
RESOURCES_CSV = Path("merged_resources.csv")
HASH_FILE     = Path("data/scraped_resources/resources_hash.txt")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_csv_hash() -> str:
    if not RESOURCES_CSV.exists():
        return ""
    return hashlib.md5(RESOURCES_CSV.read_bytes()).hexdigest()


def _save_hash() -> None:
    """Persist the current CSV hash so the next startup can detect changes."""
    h = _current_csv_hash()
    if h:
        HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
        HASH_FILE.write_text(h)
        print(f"[vector-db] Saved resources hash: {h}")


def _scrape() -> None:
    print("[vector-db] Scraping resources from merged_resources.csv ...")
    cmd = [sys.executable, "-m", "scripts.scrape_fitness_resources", "999", "ALL"]
    try:
        subprocess.run(cmd, check=True)
        print("[vector-db] Scraping complete.")
    except subprocess.CalledProcessError as exc:
        print(f"[vector-db] Scraping failed: {exc}")
        print("[vector-db] Will attempt to use existing scraped_documents.json if available.")


def _build(force: bool) -> None:
    if not SCRAPED_DATA.exists():
        print(f"[vector-db] ERROR: {SCRAPED_DATA} not found.")
        print("  Commit data/scraped_resources/scraped_documents.json to the repo, or")
        print("  run with --scrape to download resources first.")
        sys.exit(1)

    print(f"[vector-db] Building ChromaDB from {SCRAPED_DATA} (force={force}) ...")
    from app.ai_services.ai_coach.vector_db_service import initialize_vector_db

    result = initialize_vector_db(
        source_path=str(SCRAPED_DATA),
        source_type="scraped",
        force_recreate=force,
    )
    print(
        f"[vector-db] {result['status']} — "
        f"{result.get('chunks_created', '?')} chunks "
        f"in {result.get('persist_directory', '?')}"
    )
    # Always save the hash after a successful build so the next startup
    # knows the current CSV state was already processed.
    _save_hash()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="FitMind vector DB initializer")
    parser.add_argument("--force-rebuild", action="store_true",
                        help="Rebuild ChromaDB even if it already exists")
    parser.add_argument("--scrape", action="store_true",
                        help="Re-scrape resources from CSV before building")
    args = parser.parse_args()

    if args.scrape:
        _scrape()

    if not args.force_rebuild and CHROMA_PATH.exists():
        print(f"[vector-db] ChromaDB already exists at {CHROMA_PATH} — skipping.")
        return

    _build(force=args.force_rebuild)
    print("[vector-db] Done.")


if __name__ == "__main__":
    main()
