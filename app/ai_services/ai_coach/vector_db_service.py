import os
import json
import logging
import shutil
import re
from typing import List, Optional, Dict, Any, Tuple
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document

# Configure logger
logger = logging.getLogger(__name__)


class VectorDBService:
    
    # Default paths
    BASE_DIR = os.path.dirname(__file__)
    DEFAULT_PERSIST_DIR = os.path.join(BASE_DIR, "chroma_db")
    DEFAULT_PDF_PATH = os.path.join(BASE_DIR, "fitness-handbook.pdf")
    # Path to scraped documents (from scraper script)
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(BASE_DIR)))
    DEFAULT_SCRAPED_PATH = os.path.join(PROJECT_ROOT, "data", "scraped_resources", "scraped_documents.json")
    
    # Embedding model configuration
    EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
    COLLECTION_NAME = "fitness_knowledge"

    # Retrieval layers / sectioning
    WORKOUT_KEYWORDS = {
        "programming": ["programming", "guideline", "program design", "periodization", "prescription", "resistance training"],
        "exercise_library": ["exercise database", "exercise directory", "exercise anatomy", "kinesiology", "muscle directory"],
        "periodization": ["periodization", "hypertrophy", "strength", "power", "endurance"],
        "cardio": ["cardio", "aerobic", "hiit", "interval", "endurance"],
        "core": ["core", "stability", "plank", "anti-rotation"],
        "books": ["handbook", "manual", "book", "guide"],
    }
    NUTRITION_KEYWORDS = {
        "guidelines": ["nutrition", "diet", "healthy diet", "nutrition guidelines"],
        "database": ["fooddata central", "food database", "nutrient database", "usda"],
        "sports_nutrition": ["sports nutrition", "supplement", "nutrient timing", "protein"],
        "macros_tdee": ["macro", "tdee", "calorie", "macronutrient", "energy expenditure"],
        "books": ["guide", "handbook", "book", "manual"],
    }
    
    # Text splitting configuration
    # 2200 chars is a practical approximation for ~512 tokens in English text.
    CHUNK_SIZE = 2200
    CHUNK_OVERLAP = 200
    MAX_CONTEXT_CHARS = 3600
    LEXICAL_TOP_K = 24
    SEMANTIC_TOP_K_MULTIPLIER = 4
    
    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: Optional[str] = None
    ):
        """
        Initialize the VectorDBService.
        
        Args:
            persist_directory: Directory to store the ChromaDB data
            collection_name: Name of the Chroma collection
        """
        self.persist_directory = persist_directory or self.DEFAULT_PERSIST_DIR
        self.collection_name = collection_name or self.COLLECTION_NAME
        self._embeddings = None
        self._vectorstore = None
    
    @property
    def embeddings(self) -> HuggingFaceEmbeddings:
        """Lazy load embeddings model."""
        if self._embeddings is None:
            self._embeddings = HuggingFaceEmbeddings(
                model_name=self.EMBEDDING_MODEL_NAME
            )
        return self._embeddings
    
    @property
    def vectorstore(self) -> Chroma:
        """
        Lazy load or create the vector store.
        Returns existing vectorstore if already loaded.
        """
        if self._vectorstore is None:
            self._vectorstore = self._load_vectorstore()
        return self._vectorstore
    
    def _load_vectorstore(self) -> Chroma:
        """Load existing vectorstore from disk."""
        if not os.path.exists(self.persist_directory):
            raise FileNotFoundError(
                f"Vector database not found at {self.persist_directory}. "
                "Please run create_vector_db() first."
            )
        
        return Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.persist_directory
        )

    def _infer_domain(self, text: str) -> str:
        """Infer a high-level domain from content or query text."""
        lowered = (text or "").lower()
        nutrition_signals = [
            "nutrition", "diet", "meal", "food", "calorie", "macro",
            "tdee", "protein", "carb", "fat", "supplement",
        ]
        workout_signals = [
            "workout", "exercise", "training", "strength", "cardio", "program",
            "periodization", "core", "mobility", "resistance",
        ]

        nutrition_score = sum(1 for term in nutrition_signals if term in lowered)
        workout_score = sum(1 for term in workout_signals if term in lowered)

        if nutrition_score > workout_score:
            return "nutrition"
        if workout_score > nutrition_score:
            return "workout"
        return "general"

    def _infer_topic(self, domain: str, text: str) -> str:
        """Infer a narrower topic within a domain for layered filtering."""
        lowered = (text or "").lower()
        keywords_map = self.NUTRITION_KEYWORDS if domain == "nutrition" else self.WORKOUT_KEYWORDS

        for topic, keywords in keywords_map.items():
            if any(keyword in lowered for keyword in keywords):
                return topic
        return "general"

    def _cleanup_existing_store(self) -> None:
        """Remove the existing vector DB directory before a forced rebuild."""
        if os.path.exists(self.persist_directory):
            shutil.rmtree(self.persist_directory)
            logger.info("🧹 Removed existing vector DB at %s", self.persist_directory)

    def _clean_text(self, text: str) -> str:
        """Normalize scraped text before chunking and embedding."""
        if not text:
            return ""

        cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r"\u00a0", " ", cleaned)
        return cleaned.strip()

    def _is_low_quality_document(self, text: str) -> bool:
        """Heuristic filter for navigation-heavy or boilerplate-only pages."""
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
        marker_hits = sum(1 for marker in boilerplate_markers if marker in lowered)
        if marker_hits >= 5:
            return True

        unique_tokens = set(self._tokenize(lowered))
        lexical_diversity = len(unique_tokens) / max(word_count, 1)
        if word_count > 300 and lexical_diversity < 0.08:
            return True

        return False

    def _extract_keywords(self, text: str, max_keywords: int = 8) -> List[str]:
        """Extract simple keywords for retrieval diagnostics and prompt grounding."""
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", (text or "").lower())
        stop_words = {
            "the", "and", "for", "with", "that", "this", "from", "into", "your", "you", "are",
            "was", "were", "have", "has", "had", "not", "can", "may", "will", "about", "their",
            "than", "then", "also", "when", "what", "where", "which", "while", "using", "used",
            "these", "those", "over", "under", "between", "within", "should", "could", "would",
        }
        counts: Dict[str, int] = {}
        for token in tokens:
            if token in stop_words:
                continue
            counts[token] = counts.get(token, 0) + 1

        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [token for token, _ in ranked[:max_keywords]]

    def _summarize_text(self, text: str) -> str:
        """Create a compact two-line summary for metadata and context rendering."""
        if not text:
            return ""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        summary = " ".join([s.strip() for s in sentences if s.strip()][:2])
        return summary[:260]

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[a-zA-Z0-9\-]{3,}", (text or "").lower())

    def _lexical_overlap_score(self, query: str, content: str) -> float:
        query_tokens = set(self._tokenize(query))
        if not query_tokens:
            return 0.0
        content_tokens = set(self._tokenize(content))
        if not content_tokens:
            return 0.0
        overlap = len(query_tokens.intersection(content_tokens))
        return overlap / max(len(query_tokens), 1)

    def _expand_query(self, query: str) -> List[str]:
        """Generate retrieval-oriented query variants (lightweight query transformation)."""
        base = (query or "").strip()
        if not base:
            return []

        variants = [base]
        short_query = len(base.split()) <= 8
        if short_query:
            variants.append(f"{base} guidelines")
            variants.append(f"{base} best practices")
            variants.append(f"{base} safety recommendations")
        else:
            variants.append(f"summary of {base}")
            variants.append(f"evidence for {base}")

        deduped: List[str] = []
        seen = set()
        for variant in variants:
            key = variant.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(variant)
        return deduped

    def _format_filters(self, filters: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Format filters for ChromaDB query methods."""
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
    
    def _load_scraped_documents(self, json_path: str) -> List[Document]:
        """
        Load scraped documents from JSON file.
        
        Args:
            json_path: Path to scraped_documents.json
            
        Returns:
            List of LangChain Document objects
        """
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"Scraped documents not found at {json_path}")
        
        print(f"📄 Loading scraped documents from: {json_path}")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle both list format (from scraper) and dict format
        scraped_docs = data if isinstance(data, list) else data.get('documents', [])
        
        documents = []
        seen_signatures = set()
        for doc in scraped_docs:
            domain = self._infer_domain(
                " ".join([
                    doc.get("category", ""),
                    doc.get("resource_name", doc.get("title", "")),
                    doc.get("description", ""),
                    doc.get("content", "")[:1000],
                ])
            )
            topic = self._infer_topic(
                domain,
                " ".join([
                    doc.get("category", ""),
                    doc.get("resource_name", doc.get("title", "")),
                    doc.get("key_features", ""),
                    doc.get("description", ""),
                ])
            )

            # Create LangChain Document with metadata
            content = self._clean_text(doc.get('content', ''))
            if len(content) < 120:
                continue
            if self._is_low_quality_document(content):
                continue

            signature = hash(content[:2000])
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)

            documents.append(Document(
                page_content=content,
                metadata={
                    'source': doc['url'],
                    'title': doc.get('resource_name', doc.get('title', 'Unknown')),
                    'category': doc.get('category', 'Unknown'),
                    'section': doc.get('section', 'Unknown'),
                    'domain': domain,
                    'topic': topic,
                    'organization': doc.get('organization', 'Unknown'),
                    'scraped_at': doc.get('scraped_at', '')
                }
            ))
        
        print(f"✓ Loaded {len(documents)} documents from JSON")
        return documents
    
    def _load_pdf_documents(self, pdf_path: str) -> List[Document]:
        """
        Load documents from PDF file (legacy method).
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of LangChain Document objects
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found at {pdf_path}")
        
        print(f"📄 Loading PDF file: {pdf_path}")
        loader = PyPDFLoader(pdf_path)
        documents = loader.load()
        print(f"✓ Loaded {len(documents)} pages from PDF")
        return documents
    
    def create_vector_db(
        self,
        source_path: Optional[str] = None,
        source_type: str = "scraped",  # "scraped" or "pdf"
        force_recreate: bool = False
    ) -> dict:
        """
        Create the vector database from scraped documents or PDF file.
        
        Args:
            source_path: Path to source file (JSON for scraped, PDF for pdf)
            source_type: Type of source - "scraped" (default) or "pdf"
            force_recreate: If True, recreate even if DB exists
            
        Returns:
            Dictionary with creation statistics
        """
        # Check if database already exists
        if os.path.exists(self.persist_directory) and not force_recreate:
            return {
                "status": "exists",
                "message": f"Vector database already exists at {self.persist_directory}",
                "persist_directory": self.persist_directory
            }

        if force_recreate:
            self._cleanup_existing_store()
        
        # Load documents based on source type
        if source_type == "scraped":
            source_path = source_path or self.DEFAULT_SCRAPED_PATH
            documents = self._load_scraped_documents(source_path)
        elif source_type == "pdf":
            source_path = source_path or self.DEFAULT_PDF_PATH
            documents = self._load_pdf_documents(source_path)
        else:
            raise ValueError(f"Invalid source_type: {source_type}. Must be 'scraped' or 'pdf'")
        
        # Split documents into chunks
        print("✂️ Splitting documents into chunks...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.CHUNK_SIZE,
            chunk_overlap=self.CHUNK_OVERLAP,
            separators=["\n\n", "\n", " ", ""]
        )
        split_docs = text_splitter.split_documents(documents)

        texts: List[Document] = []
        for idx, doc in enumerate(split_docs):
            cleaned_content = self._clean_text(doc.page_content)
            if len(cleaned_content) < 80:
                continue
            doc.page_content = cleaned_content
            doc.metadata = dict(doc.metadata or {})
            doc.metadata["chunk_index"] = idx
            doc.metadata["chunk_summary"] = self._summarize_text(cleaned_content)
            doc.metadata["chunk_keywords"] = ", ".join(self._extract_keywords(cleaned_content))
            texts.append(doc)

        print(f"📝 Created {len(texts)} text chunks")
        
        # Create vector store
        print("🔧 Creating and saving vector store...")
        self._vectorstore = Chroma.from_documents(
            documents=texts,
            embedding=self.embeddings,
            collection_name=self.collection_name,
            persist_directory=self.persist_directory
        )
        print(f"✅ Vector store saved in: {self.persist_directory}")
        
        return {
            "status": "created",
            "message": "Vector database created successfully",
            "source_type": source_type,
            "source_path": source_path,
            "documents_loaded": len(documents),
            "chunks_created": len(texts),
            "persist_directory": self.persist_directory,
            "collection_name": self.collection_name
        }
    
    def similarity_search(
        self,
        query: str,
        k: int = 3,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """
        Search for similar documents in the vector store.
        
        Args:
            query: Search query
            k: Number of results to return
            filters: Dictionary of filters applying to metadata
            
        Returns:
            List of relevant document contents
        """
        formatted_filter = self._format_filters(filters)

        query_variants = self._expand_query(query)
        semantic_k = max(k * self.SEMANTIC_TOP_K_MULTIPLIER, k + 4)
        lexical_k = max(k * 3, self.LEXICAL_TOP_K)

        candidate_scores: Dict[str, Tuple[float, Document]] = {}

        def _doc_key(doc: Document) -> str:
            source = doc.metadata.get("source", "")
            title = doc.metadata.get("title", "")
            chunk_index = doc.metadata.get("chunk_index", "")
            return f"{source}|{title}|{chunk_index}|{hash(doc.page_content)}"

        for variant in query_variants:
            semantic_results = self.vectorstore.similarity_search_with_relevance_scores(
                variant,
                k=semantic_k,
                filter=formatted_filter,
            )
            for doc, semantic_score in semantic_results:
                lexical_score = self._lexical_overlap_score(query, doc.page_content)
                combined_score = (semantic_score * 0.70) + (lexical_score * 0.30)
                key = _doc_key(doc)
                previous = candidate_scores.get(key)
                if previous is None or combined_score > previous[0]:
                    candidate_scores[key] = (combined_score, doc)

            lexical_candidates = self.vectorstore.similarity_search(
                variant,
                k=lexical_k,
                filter=formatted_filter,
            )
            for doc in lexical_candidates:
                lexical_score = self._lexical_overlap_score(query, doc.page_content)
                if lexical_score <= 0:
                    continue
                semantic_hint = 0.45
                combined_score = (semantic_hint * 0.70) + (lexical_score * 0.30)
                key = _doc_key(doc)
                previous = candidate_scores.get(key)
                if previous is None or combined_score > previous[0]:
                    candidate_scores[key] = (combined_score, doc)

        ranked_candidates = sorted(candidate_scores.values(), key=lambda item: item[0], reverse=True)
        results = [doc for _, doc in ranked_candidates[:k]]
        
        # Log retrieved documents
        logger.info(f"\n{'='*70}")
        logger.info(f"📊 Vector DB Query")
        logger.info(f"{'='*70}")
        logger.info(f"Query: {query}")
        if filters:
            logger.info(f"Filters: {filters}")
        logger.info(f"Retrieved {len(results)} documents")
        
        for idx, doc in enumerate(results, 1):
            logger.info(f"\n--- Document {idx} ---")
            logger.info(f"Source: {doc.metadata.get('source', 'Unknown')}")
            logger.info(f"Title: {doc.metadata.get('title', 'Unknown')}")
            logger.info(f"Category: {doc.metadata.get('category', 'Unknown')}")
            logger.info(f"Organization: {doc.metadata.get('organization', 'Unknown')}")
            logger.info(f"Content preview: {doc.page_content[:200]}...")
        
        logger.info(f"{'='*70}\n")
        
        return results
    
    def get_context(
        self,
        query: str,
        k: int = 3,
        domain: Optional[str] = None,
        topic: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Get concatenated context from similar documents.
        
        Args:
            query: Search query
            k: Number of documents to retrieve
            
        Returns:
            Concatenated context string
        """
        effective_filters: Dict[str, Any] = dict(filters or {})

        inferred_domain = domain or self._infer_domain(query)
        if inferred_domain in ("workout", "nutrition"):
            effective_filters.setdefault("domain", inferred_domain)

        inferred_topic = topic or self._infer_topic(inferred_domain, query)
        if inferred_topic != "general":
            effective_filters.setdefault("topic", inferred_topic)

        documents = self.similarity_search(query, k=k, filters=effective_filters or None)

        # Fallback: if the filtered retrieval is too narrow, broaden it in two steps
        # rather than returning too little context.
        if effective_filters and len(documents) < max(1, k // 2):
            if "topic" in effective_filters:
                broader_filters = dict(effective_filters)
                broader_filters.pop("topic", None)
                logger.info(
                    "Broadening retrieval for query '%s' by removing topic filter: %s",
                    query,
                    broader_filters,
                )
                documents = self.similarity_search(query, k=k, filters=broader_filters)

        if effective_filters and not documents:
            logger.info("Broadening retrieval for query '%s' by removing all filters", query)
            documents = self.similarity_search(query, k=k, filters=None)

        context_blocks = [self._build_context_block(doc) for doc in documents]
        context = "\n\n".join(context_blocks)
        context = context[:self.MAX_CONTEXT_CHARS].rstrip()
        
        logger.info(f"📝 Total context length: {len(context)} characters")
        
        return context
    
    def is_initialized(self) -> bool:
        """Check if the vector database is initialized."""
        return os.path.exists(self.persist_directory)


# Singleton instance for the application
_vector_db_service: Optional[VectorDBService] = None


def get_vector_db_service() -> VectorDBService:
    """
    Get the singleton VectorDBService instance.
    
    Returns:
        VectorDBService instance
    """
    global _vector_db_service
    if _vector_db_service is None:
        _vector_db_service = VectorDBService()
    return _vector_db_service


def initialize_vector_db(
    force_recreate: bool = False,
    source_path: Optional[str] = None,
    source_type: str = "scraped"
) -> dict:
    """
    Initialize the vector database.
    This should be called once during application setup.
    
    Args:
        force_recreate: If True, recreate even if DB exists
        source_path: Path to source file (JSON for scraped, PDF for pdf)
        source_type: Type of source - "scraped" (default) or "pdf"
        
    Returns:
        Dictionary with initialization status
    """
    service = get_vector_db_service()
    return service.create_vector_db(
        source_path=source_path,
        source_type=source_type,
        force_recreate=force_recreate
    )


if __name__ == "__main__":
    # Run this script directly to create the vector database
    print("=" * 60)
    print("🏋️ FitMind AI Coach - Vector Database Initialization")
    print("=" * 60)
    
    result = initialize_vector_db(force_recreate=False)
    
    print("\n📊 Result:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    
    print("\n" + "=" * 60)
    print("✅ Vector database initialization complete!")
    print("=" * 60)
