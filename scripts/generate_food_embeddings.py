"""
Populate / refresh name_embedding for all active central_foods rows.

Run after changing the embedding model to regenerate all vectors:

    python -m scripts.generate_food_embeddings

Set DATABASE_URL in your environment (or .env) before running.
Batch-processes 256 rows at a time to avoid memory spikes.
"""
import os
import sys
import logging
from sqlalchemy import create_engine, text
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/fitmind")
EMBEDDING_MODEL = os.getenv("AI_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
BATCH_SIZE = 256


def _vec_str(vec) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


def main():
    engine = create_engine(DATABASE_URL)
    logger.info("Loading embedding model %s …", EMBEDDING_MODEL)
    model = SentenceTransformer(EMBEDDING_MODEL)

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text(
            "ALTER TABLE central_foods "
            "ADD COLUMN IF NOT EXISTS name_embedding vector(384)"
        ))
        conn.commit()

        all_rows = conn.execute(
            text(
                "SELECT id, food_name, food_name_ar, food_category, dietary_tags "
                "FROM central_foods WHERE is_active = true ORDER BY id"
            ),
        ).fetchall()

        total = len(all_rows)
        logger.info("%d foods to embed.", total)

        if total == 0:
            logger.info("Nothing to do.")
            return

        processed = 0
        for batch_start in range(0, total, BATCH_SIZE):
            batch = all_rows[batch_start: batch_start + BATCH_SIZE]
            # Embed name + category + tags (+ Arabic name when present), not
            # just the bare name — a bare dish name (e.g. "Molokhia") has no
            # lexical/semantic overlap with a category-style retrieval query
            # (e.g. "Egyptian vegetables fruits salad greens"), so it
            # consistently loses the similarity race against generic USDA rows
            # whose names ARE the category words (e.g. "Spinach, raw").
            # Including category/tags/Arabic name gives the embedding real
            # content to match against.
            names = [
                f"{r.food_name} {r.food_name_ar or ''} ({r.food_category or ''}) "
                f"{' '.join(r.dietary_tags or [])}".strip()
                for r in batch
            ]
            embeddings = model.encode(names, normalize_embeddings=True, show_progress_bar=False)

            for row, emb in zip(batch, embeddings):
                conn.execute(
                    text("UPDATE central_foods SET name_embedding = CAST(:vec AS vector) WHERE id = :id"),
                    {"vec": _vec_str(emb), "id": row.id},
                )

            conn.commit()
            processed += len(batch)
            logger.info("Embedded %d / %d foods …", processed, total)

        logger.info("Creating IVFFlat index on name_embedding …")
        try:
            conn.execute(text("DROP INDEX IF EXISTS idx_central_foods_name_embedding"))
            conn.execute(text(
                "CREATE INDEX idx_central_foods_name_embedding "
                "ON central_foods USING ivfflat (name_embedding vector_cosine_ops) "
                "WITH (lists = 100)"
            ))
            conn.commit()
            logger.info("Index created.")
        except Exception as exc:
            logger.warning("Index creation skipped (may need more rows for IVFFlat): %s", exc)

    logger.info("Done. %d food embeddings written.", processed)


if __name__ == "__main__":
    main()
