"""
Populate / refresh name_embedding for all active central_exercises rows.

Run after changing the embedding model to regenerate all vectors:

    python -m scripts.generate_exercise_embeddings

Mirrors generate_food_embeddings.py — same model, same batch size, same index strategy.
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
            "ALTER TABLE central_exercises "
            "ADD COLUMN IF NOT EXISTS name_embedding vector(384)"
        ))
        conn.commit()

        all_rows = conn.execute(
            text(
                "SELECT id, name FROM central_exercises "
                "WHERE is_active = true ORDER BY id"
            ),
        ).fetchall()

        total = len(all_rows)
        logger.info("%d exercises to embed.", total)

        if total == 0:
            logger.info("Nothing to do.")
            return

        processed = 0
        for batch_start in range(0, total, BATCH_SIZE):
            batch = all_rows[batch_start: batch_start + BATCH_SIZE]
            names = [r.name for r in batch]
            embeddings = model.encode(names, normalize_embeddings=True, show_progress_bar=False)

            for row, emb in zip(batch, embeddings):
                conn.execute(
                    text("UPDATE central_exercises SET name_embedding = CAST(:vec AS vector) WHERE id = :id"),
                    {"vec": _vec_str(emb), "id": row.id},
                )

            conn.commit()
            processed += len(batch)
            logger.info("Embedded %d / %d exercises …", processed, total)

        logger.info("Creating IVFFlat index on central_exercises.name_embedding …")
        try:
            conn.execute(text("DROP INDEX IF EXISTS idx_central_exercises_name_embedding"))
            conn.execute(text(
                "CREATE INDEX idx_central_exercises_name_embedding "
                "ON central_exercises USING ivfflat (name_embedding vector_cosine_ops) "
                "WITH (lists = 100)"
            ))
            conn.commit()
            logger.info("Index created.")
        except Exception as exc:
            logger.warning("Index creation skipped: %s", exc)

    logger.info("Done. %d exercise embeddings written.", processed)


if __name__ == "__main__":
    main()
