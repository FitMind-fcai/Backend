import os
import json
import logging
import shutil
import re
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document

from app.ai_services.embedding_utils import embed_texts

logger = logging.getLogger(__name__)


class VectorDBService:
    # Default paths
    BASE_DIR = os.path.dirname(__file__)
    DEFAULT_PERSIST_DIR = os.path.join(BASE_DIR, "chroma_db")
    DEFAULT_PDF_PATH = os.path.join(BASE_DIR, "fitness-handbook.pdf")
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(BASE_DIR)))
    DEFAULT_SCRAPED_PATH = os.path.join(
        PROJECT_ROOT, "data", "scraped_resources", "scraped_documents.json"
    )

    # Embedding model configuration
    EMBEDDING_MODEL_NAME = os.getenv(
        "AI_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
    )
    COLLECTION_NAME = "fitness_knowledge"

    # Retrieval layers / sectioning
    WORKOUT_KEYWORDS = {
        "programming": [
            "programming",
            "guideline",
            "program design",
            "periodization",
            "prescription",
            "resistance training",
        ],
        "exercise_library": [
            "exercise database",
            "exercise directory",
            "exercise anatomy",
            "kinesiology",
            "muscle directory",
        ],
        "periodization": [
            "periodization",
            "hypertrophy",
            "strength",
            "power",
            "endurance",
        ],
        "cardio": ["cardio", "aerobic", "hiit", "interval", "endurance"],
        "core": ["core", "stability", "plank", "anti-rotation"],
        "books": ["handbook", "manual", "book", "guide"],
    }
    NUTRITION_KEYWORDS = {
        "guidelines": ["nutrition", "diet", "healthy diet", "nutrition guidelines"],
        "database": ["fooddata central", "food database", "nutrient database", "usda"],
        "sports_nutrition": [
            "sports nutrition",
            "supplement",
            "nutrient timing",
            "protein",
        ],
        "macros_tdee": [
            "macro",
            "tdee",
            "calorie",
            "macronutrient",
            "energy expenditure",
        ],
        "books": ["guide", "handbook", "book", "manual"],
    }

    # Text splitting configuration
    CHUNK_SIZE = 2200
    CHUNK_OVERLAP = 200
    MAX_CONTEXT_CHARS = 3600
    LEXICAL_TOP_K = 24
    SEMANTIC_TOP_K_MULTIPLIER = 4

    # Phase 4 — retrieval constants
    BM25_TOP_K = 20
    DENSE_TOP_K = 20
    RRF_K = 60  # RRF constant 

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: Optional[str] = None,
    ):
        self.persist_directory = persist_directory or self.DEFAULT_PERSIST_DIR
        self.collection_name = collection_name or self.COLLECTION_NAME

        self._embeddings = None
        self._vectorstore = None
        self._bm25_index = None
        self._bm25_docs: List[Dict[str, Any]] = []

        self._lazy_lock = threading.RLock()

    # ------------------------------------------------------------------
    # Lazy-loaded properties
    # ------------------------------------------------------------------

    @property
    def embeddings(self):
        if self._embeddings is None:
            with self._lazy_lock:
                if self._embeddings is None:
                    from app.ai_services.embedding_utils import get_shared_embeddings

                    self._embeddings = get_shared_embeddings()
        return self._embeddings

    @property
    def vectorstore(self) -> Chroma:
        if self._vectorstore is None:
            with self._lazy_lock:
                if self._vectorstore is None:
                    self._vectorstore = self._load_vectorstore()
        return self._vectorstore

    @property
    def bm25_index(self):
        if self._bm25_index is None:
            with self._lazy_lock:
                if self._bm25_index is None:
                    self._build_bm25_index()
        return self._bm25_index

    # ------------------------------------------------------------------
    # Phase 4 — BM25 index
    # ------------------------------------------------------------------

    def _build_bm25_index(self) -> None:
        """Build BM25 index from all documents stored in ChromaDB."""
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.warning(
                "rank_bm25 not installed — BM25 retrieval disabled. Run: pip install rank-bm25"
            )
            return

        try:
            collection = self.vectorstore._collection
            result = collection.get(include=["documents", "metadatas"])
        except Exception as exc:
            logger.warning(
                "Could not load documents from ChromaDB for BM25 indexing: %s", exc
            )
            return

        docs = result.get("documents") or []
        metas = result.get("metadatas") or []
        ids = result.get("ids") or []

        if not docs:
            logger.warning("ChromaDB collection is empty — BM25 index will be empty.")
            return

        self._bm25_docs = [
            {"text": text, "metadata": meta, "chroma_id": cid}
            for text, meta, cid in zip(docs, metas, ids)
        ]

        tokenized = [self._tokenize(d["text"]) for d in self._bm25_docs]
        self._bm25_index = BM25Okapi(tokenized)
        logger.info("BM25 index built with %d document chunks", len(self._bm25_docs))

    def _bm25_search(
        self,
        query: str,
        k: int,
        domain_filter: Optional[str] = None,
    ) -> List[Tuple[int, float]]:
        """
        Return (doc_index, score) pairs for top-k BM25 results.
        Optionally filter by domain metadata.
        """
        if self.bm25_index is None or not self._bm25_docs:
            return []

        tokens = self._tokenize(query)
        scores = self.bm25_index.get_scores(tokens)

        candidates: List[Tuple[int, float]] = []
        for idx, score in enumerate(scores):
            if score <= 0:
                continue
            if domain_filter:
                doc_domain = (self._bm25_docs[idx].get("metadata") or {}).get(
                    "domain", ""
                )
                if doc_domain and doc_domain != domain_filter:
                    continue
            candidates.append((idx, float(score)))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:k]

    # ------------------------------------------------------------------
    # Phase 4 — RRF Fusion
    # ------------------------------------------------------------------

    def _rrf_fusion(
        self,
        dense_docs: List[Document],
        bm25_hits: List[Tuple[int, float]],
    ) -> List[Document]:
        """
        Reciprocal Rank Fusion of dense-retrieval results and BM25 results.

        RRF score for document d:
            rrf(d) = Σ_ranker  1 / (RRF_K + rank_of_d_in_ranker)

        Documents that appear in both lists receive a higher combined score.
        """
        rrf_scores: Dict[str, float] = {}
        key_to_doc: Dict[str, Document] = {}

        def _doc_key(content: str) -> str:
            return content[:300]

        # Dense ranking contribution
        for rank, doc in enumerate(dense_docs):
            key = _doc_key(doc.page_content)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (self.RRF_K + rank + 1)
            key_to_doc[key] = doc

        # BM25 ranking contribution
        for rank, (idx, _score) in enumerate(bm25_hits):
            d = self._bm25_docs[idx]
            key = _doc_key(d["text"])
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (self.RRF_K + rank + 1)
            if key not in key_to_doc:
                key_to_doc[key] = Document(
                    page_content=d["text"],
                    metadata=d.get("metadata") or {},
                )

        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return [key_to_doc[k] for k, _ in ranked if k in key_to_doc]

    # ------------------------------------------------------------------
    # Vectorstore helpers
    # ------------------------------------------------------------------

    def _load_vectorstore(self) -> Chroma:
        if not os.path.exists(self.persist_directory):
            raise FileNotFoundError(
                f"Vector database not found at {self.persist_directory}. "
                "Please run create_vector_db() first."
            )
        return Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.persist_directory,
        )

    def _infer_domain(self, text: str) -> str:
        lowered = (text or "").lower()
        nutrition_signals = [
            "nutrition",
            "diet",
            "meal",
            "food",
            "calorie",
            "macro",
            "tdee",
            "protein",
            "carb",
            "fat",
            "supplement",
        ]
        workout_signals = [
            "workout",
            "exercise",
            "training",
            "strength",
            "cardio",
            "program",
            "periodization",
            "core",
            "mobility",
            "resistance",
        ]
        n = sum(1 for t in nutrition_signals if t in lowered)
        w = sum(1 for t in workout_signals if t in lowered)
        if n > w:
            return "nutrition"
        if w > n:
            return "workout"
        return "general"

    def _infer_topic(self, domain: str, text: str) -> str:
        lowered = (text or "").lower()
        keywords_map = (
            self.NUTRITION_KEYWORDS if domain == "nutrition" else self.WORKOUT_KEYWORDS
        )
        for topic, keywords in keywords_map.items():
            if any(keyword in lowered for keyword in keywords):
                return topic
        return "general"

    def _cleanup_existing_store(self) -> None:
        path = Path(self.persist_directory)
        if not path.exists():
            return
        for item in path.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        logger.info("Cleared existing vector DB at %s", self.persist_directory)

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r" ", " ", cleaned)
        return cleaned.strip()

    def _is_low_quality_document(self, text: str) -> bool:
        lowered = (text or "").lower()
        word_count = len(lowered.split())
        if word_count < 60:
            return True
        boilerplate_markers = [
            "about nsca",
            "membership overview",
            "contact us",
            "privacy policy",
            "terms of use",
            "become a member",
            "report ceus",
            "login",
            "shop",
            "donate",
            "all rights reserved",
        ]
        low_quality_markers = [
            "calculator result",
            "blog post",
            "read more articles",
            "leave a comment",
        ]
        if sum(1 for m in boilerplate_markers if m in lowered) >= 5:
            return True
        if sum(1 for m in low_quality_markers if m in lowered) >= 2:
            return True
        unique_tokens = set(self._tokenize(lowered))
        lexical_diversity = len(unique_tokens) / max(word_count, 1)
        if word_count > 300 and lexical_diversity < 0.08:
            return True
        return False

    def _extract_keywords(self, text: str, max_keywords: int = 8) -> List[str]:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", (text or "").lower())
        stop_words = {
            "the",
            "and",
            "for",
            "with",
            "that",
            "this",
            "from",
            "into",
            "your",
            "you",
            "are",
            "was",
            "were",
            "have",
            "has",
            "had",
            "not",
            "can",
            "may",
            "will",
            "about",
            "their",
            "than",
            "then",
            "also",
            "when",
            "what",
            "where",
            "which",
            "while",
            "using",
            "used",
            "these",
            "those",
            "over",
            "under",
            "between",
            "within",
            "should",
            "could",
            "would",
        }
        counts: Dict[str, int] = {}
        for token in tokens:
            if token not in stop_words:
                counts[token] = counts.get(token, 0) + 1
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [token for token, _ in ranked[:max_keywords]]

    def _summarize_text(self, text: str) -> str:
        if not text:
            return ""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        summary = " ".join([s.strip() for s in sentences if s.strip()][:2])
        return summary[:260]

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[a-zA-Z0-9\-]{3,}", (text or "").lower())

    def _expand_query(self, query: str) -> List[str]:
        base = (query or "").strip()
        if not base:
            return []
        variants = [base]
        if len(base.split()) <= 8:
            variants += [
                f"{base} guidelines",
                f"{base} best practices",
                f"{base} safety recommendations",
            ]
        else:
            variants += [f"summary of {base}", f"evidence for {base}"]
        seen: set = set()
        deduped: List[str] = []
        for v in variants:
            if v.lower() not in seen:
                seen.add(v.lower())
                deduped.append(v)
        return deduped

    def _format_filters(
        self, filters: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not filters:
            return None
        if len(filters) > 1:
            return {"$and": [{k: v} for k, v in filters.items()]}
        return filters

    def _build_context_block(self, document: Document) -> str:
        source = document.metadata.get("source", "Unknown")
        title = document.metadata.get("title", "Unknown")
        summary = document.metadata.get("chunk_summary", "")
        keywords = document.metadata.get("chunk_keywords", "")
        text = (document.page_content or "").strip()
        if len(text) > 900:
            text = text[:900].rstrip() + "..."
        return (
            f"[SOURCE: {title} | {source}]\n"
            f"Summary: {summary}\n"
            f"Keywords: {keywords}\n"
            f"Content: {text}"
        )

    # ------------------------------------------------------------------
    # Document loading (unchanged from original)
    # ------------------------------------------------------------------

    def _load_scraped_documents(self, json_path: str) -> List[Document]:
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"Scraped documents not found at {json_path}")
        print(f"Loading scraped documents from: {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        scraped_docs = data if isinstance(data, list) else data.get("documents", [])
        documents = []
        seen_sigs: set = set()
        for doc in scraped_docs:
            domain = self._infer_domain(
                " ".join(
                    [
                        doc.get("category", ""),
                        doc.get("resource_name", doc.get("title", "")),
                        doc.get("description", ""),
                        doc.get("content", "")[:1000],
                    ]
                )
            )
            topic = self._infer_topic(
                domain,
                " ".join(
                    [
                        doc.get("category", ""),
                        doc.get("resource_name", doc.get("title", "")),
                        doc.get("key_features", ""),
                        doc.get("description", ""),
                    ]
                ),
            )
            content = self._clean_text(doc.get("content", ""))
            if len(content) < 120:
                continue
            if self._is_low_quality_document(content):
                continue
            sig = hash(content[:2000])
            if sig in seen_sigs:
                continue
            seen_sigs.add(sig)
            documents.append(
                Document(
                    page_content=content,
                    metadata={
                        "source": doc["url"],
                        "title": doc.get("resource_name", doc.get("title", "Unknown")),
                        "category": doc.get("category", "Unknown"),
                        "section": doc.get("section", "Unknown"),
                        "domain": domain,
                        "topic": topic,
                        "organization": doc.get("organization", "Unknown"),
                        "scraped_at": doc.get("scraped_at", ""),
                    },
                )
            )
        print(f"Loaded {len(documents)} documents from JSON")
        return documents

    def _load_pdf_documents(self, pdf_path: str) -> List[Document]:
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found at {pdf_path}")
        print(f"Loading PDF file: {pdf_path}")
        loader = PyPDFLoader(pdf_path)
        documents = loader.load()
        print(f"Loaded {len(documents)} pages from PDF")
        return documents

    # ------------------------------------------------------------------
    # Vector DB creation
    # ------------------------------------------------------------------

    def create_vector_db(
        self,
        source_path: Optional[str] = None,
        source_type: str = "scraped",
        force_recreate: bool = False,
    ) -> dict:
        if os.path.exists(self.persist_directory) and not force_recreate:
            return {
                "status": "exists",
                "message": f"Vector database already exists at {self.persist_directory}",
                "persist_directory": self.persist_directory,
            }
        if force_recreate:
            self._cleanup_existing_store()

        if source_type == "scraped":
            source_path = source_path or self.DEFAULT_SCRAPED_PATH
            documents = self._load_scraped_documents(source_path)
        elif source_type == "pdf":
            source_path = source_path or self.DEFAULT_PDF_PATH
            documents = self._load_pdf_documents(source_path)
        else:
            raise ValueError(
                f"Invalid source_type: {source_type}. Must be 'scraped' or 'pdf'"
            )

        print("Splitting documents into chunks...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.CHUNK_SIZE,
            chunk_overlap=self.CHUNK_OVERLAP,
            separators=["\n\n", "\n", " ", ""],
        )
        split_docs = text_splitter.split_documents(documents)

        texts: List[Document] = []
        for idx, doc in enumerate(split_docs):
            cleaned = self._clean_text(doc.page_content)
            if len(cleaned) < 80:
                continue
            doc.page_content = cleaned
            doc.metadata = dict(doc.metadata or {})
            doc.metadata["chunk_index"] = idx
            doc.metadata["chunk_summary"] = self._summarize_text(cleaned)
            doc.metadata["chunk_keywords"] = ", ".join(self._extract_keywords(cleaned))
            texts.append(doc)

        print(f"Created {len(texts)} text chunks")
        print("Creating and saving vector store...")
        self._vectorstore = Chroma.from_documents(
            documents=texts,
            embedding=self.embeddings,
            collection_name=self.collection_name,
            persist_directory=self.persist_directory,
        )
        # Invalidate BM25 index so it gets rebuilt on next retrieval
        self._bm25_index = None
        self._bm25_docs = []
        print(f"Vector store saved in: {self.persist_directory}")

        return {
            "status": "created",
            "message": "Vector database created successfully",
            "source_type": source_type,
            "source_path": source_path,
            "documents_loaded": len(documents),
            "chunks_created": len(texts),
            "persist_directory": self.persist_directory,
            "collection_name": self.collection_name,
        }

    # ------------------------------------------------------------------
    # Phase 4 — Hybrid retrieval: Dense + BM25 + RRF + Reranker
    # ------------------------------------------------------------------

    def similarity_search(
        self,
        query: str,
        k: int = 3,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """
        Hybrid retrieval pipeline:
          1. Dense retrieval  — top DENSE_TOP_K results per query variant
          2. BM25 retrieval   — top BM25_TOP_K results
          3. RRF Fusion       — combine both ranked lists → final top-k
        """
        formatted_filter = self._format_filters(filters)
        domain_filter = (filters or {}).get("domain") if filters else None

        # ── Step 1: Dense retrieval across query variants ──────────────
        query_variants = self._expand_query(query)
        dense_seen: Dict[str, Tuple[float, Document]] = {}

        def _doc_key(doc: Document) -> str:
            src = doc.metadata.get("source", "")
            title = doc.metadata.get("title", "")
            cidx = doc.metadata.get("chunk_index", "")
            return f"{src}|{title}|{cidx}|{hash(doc.page_content)}"

        semantic_k = max(k * self.SEMANTIC_TOP_K_MULTIPLIER, self.DENSE_TOP_K)
        variant_embeddings = embed_texts(query_variants)
        relevance_score_fn = self.vectorstore._select_relevance_score_fn()

        for embedding in variant_embeddings:
            raw_results = (
                self.vectorstore.similarity_search_by_vector_with_relevance_scores(
                    embedding,
                    k=semantic_k,
                    filter=formatted_filter,
                )
            )
            results = [(doc, relevance_score_fn(score)) for doc, score in raw_results]
            for doc, score in results:
                # Gold-source boost / blog penalty
                title = doc.metadata.get("title", "").lower()
                source = doc.metadata.get("source", "").lower()
                gold = ["acsm", "nsca", "who", "issn", "ioc", "nih"]
                if any(g in title or g in source for g in gold):
                    score += 0.15
                if "blog" in source or "calculator" in source or "blog" in title:
                    score -= 0.20
                key = _doc_key(doc)
                if key not in dense_seen or score > dense_seen[key][0]:
                    dense_seen[key] = (score, doc)

        # Sort dense results by combined score
        dense_docs: List[Document] = [
            doc
            for _, doc in sorted(dense_seen.values(), key=lambda x: x[0], reverse=True)
        ]

        # ── Step 2: BM25 retrieval ─────────────────────────────────────
        bm25_hits = self._bm25_search(
            query, k=self.BM25_TOP_K, domain_filter=domain_filter
        )

        # ── Step 3: RRF Fusion → take top-k ───────────────────────────
        fused_docs = self._rrf_fusion(dense_docs, bm25_hits)
        final_docs = fused_docs[:k]

        # ── Logging ────────────────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("Hybrid RAG Query: %s", query)
        logger.info(
            "Dense candidates: %d | BM25 hits: %d | After RRF: %d | Final: %d",
            len(dense_docs),
            len(bm25_hits),
            len(fused_docs),
            len(final_docs),
        )
        for idx, doc in enumerate(final_docs, 1):
            logger.info(
                "  [%d] %s | %s | %s",
                idx,
                doc.metadata.get("title", "?"),
                doc.metadata.get("source", "?"),
                doc.page_content[:120],
            )
        logger.info("=" * 60)

        return final_docs

    # ------------------------------------------------------------------
    # Context assembly
    # ------------------------------------------------------------------

    def get_context(
        self,
        query: str,
        k: int = 3,
        domain: Optional[str] = None,
        topic: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> str:
        effective_filters: Dict[str, Any] = dict(filters or {})

        inferred_domain = domain or self._infer_domain(query)
        if inferred_domain in ("workout", "nutrition"):
            effective_filters.setdefault("domain", inferred_domain)

        inferred_topic = topic or self._infer_topic(inferred_domain, query)
        if inferred_topic != "general":
            effective_filters.setdefault("topic", inferred_topic)

        documents = self.similarity_search(
            query, k=k, filters=effective_filters or None
        )

        # Broadening fallback: if results are too few, relax filters progressively
        if effective_filters and len(documents) < max(1, k // 2):
            if "topic" in effective_filters:
                broader = dict(effective_filters)
                broader.pop("topic", None)
                logger.info("Broadening retrieval — removing topic filter: %s", broader)
                documents = self.similarity_search(query, k=k, filters=broader)

        if effective_filters and not documents:
            logger.info("Broadening retrieval — removing all filters")
            documents = self.similarity_search(query, k=k, filters=None)

        context_blocks = [self._build_context_block(doc) for doc in documents]
        context = "\n\n".join(context_blocks)
        context = context[: self.MAX_CONTEXT_CHARS].rstrip()

        logger.info("Total context length: %d characters", len(context))
        return context

    def is_initialized(self) -> bool:
        return os.path.exists(self.persist_directory)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_vector_db_service: Optional[VectorDBService] = None
_vector_db_service_lock = threading.Lock()


def get_vector_db_service() -> VectorDBService:
    global _vector_db_service
    if _vector_db_service is None:
        with _vector_db_service_lock:
            if _vector_db_service is None:
                _vector_db_service = VectorDBService()
    return _vector_db_service


def initialize_vector_db(
    force_recreate: bool = False,
    source_path: Optional[str] = None,
    source_type: str = "scraped",
) -> dict:
    service = get_vector_db_service()
    return service.create_vector_db(
        source_path=source_path,
        source_type=source_type,
        force_recreate=force_recreate,
    )


if __name__ == "__main__":
    print("=" * 60)
    print("FitMind AI Coach - Vector Database Initialization")
    print("=" * 60)
    result = initialize_vector_db(force_recreate=False)
    print("\nResult:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    print("=" * 60)
