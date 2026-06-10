"""
Populate name_embedding for all central_exercises rows that currently have NULL embeddings.

Run once after deploying the pgvector changes:

    python -m scripts.generate_exercise_embeddings

Mirrors generate_food_embeddings.py — same model, same batch size, same index strategy.
"""
import os
import sys
import logging

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/fitmind")
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
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

        total = conn.execute(
            text("SELECT COUNT(*) FROM central_exercises WHERE is_active = true AND name_embedding IS NULL")
        ).scalar()
        logger.info("%d exercises need embeddings.", total)

        if total == 0:
            logger.info("Nothing to do.")
            return

        offset = 0
        processed = 0
        while True:
            rows = conn.execute(
                text(
                    "SELECT id, name FROM central_exercises "
                    "WHERE is_active = true AND name_embedding IS NULL "
                    "LIMIT :lim OFFSET :off"
                ),
                {"lim": BATCH_SIZE, "off": offset},
            ).fetchall()
            if not rows:
                break

            names = [r.name for r in rows]
            embeddings = model.encode(names, normalize_embeddings=True, show_progress_bar=False)

            for row, emb in zip(rows, embeddings):
                conn.execute(
                    text("UPDATE central_exercises SET name_embedding = :vec::vector WHERE id = :id"),
                    {"vec": _vec_str(emb), "id": row.id},
                )

            conn.commit()
            processed += len(rows)
            logger.info("Embedded %d / %d exercises …", processed, total)
            offset += BATCH_SIZE

        logger.info("Creating IVFFlat index on central_exercises.name_embedding …")
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_central_exercises_name_embedding "
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
