"""
Shared embedding utility used by meal scanner, voice transcriber, and any other
service that needs semantic vector search against central_foods / central_exercises.

Model is configured via AI_EMBEDDING_MODEL in .env.
Loaded lazily as a module-level singleton so the weights are downloaded
and cached once per process.
"""
import os
import logging
from typing import List

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = os.getenv("AI_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
EMBEDDING_DIM = 384

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model %s …", EMBEDDING_MODEL_NAME)
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def embed_text(text: str) -> List[float]:
    """Encode *text* and return a unit-norm embedding vector (list of floats)."""
    vec = _get_model().encode(text, normalize_embeddings=True)
    return vec.tolist()


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Batch-encode multiple strings; returns one embedding per input."""
    vecs = _get_model().encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def vec_to_pg_str(embedding: List[float]) -> str:
    """Format a float list as a pgvector literal: '[0.1,0.2,…]'."""
    return "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"


class SharedHuggingFaceEmbeddings:
    """LangChain-compatible embedding wrapper that reuses the singleton model."""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._encode(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._encode(text)

    def _encode(self, text: str) -> List[float]:
        vec = _get_model().encode(text, normalize_embeddings=True)
        return vec.tolist()


_shared_embeddings = None


def get_shared_embeddings() -> SharedHuggingFaceEmbeddings:
    global _shared_embeddings
    if _shared_embeddings is None:
        _get_model()
        _shared_embeddings = SharedHuggingFaceEmbeddings()
    return _shared_embeddings
