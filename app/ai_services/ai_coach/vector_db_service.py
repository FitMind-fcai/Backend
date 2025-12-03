import os
import json
import logging
from typing import List, Optional, Dict, Any
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
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(BASE_DIR))))
    DEFAULT_SCRAPED_PATH = os.path.join(PROJECT_ROOT, "data", "scraped_resources", "scraped_documents.json")
    
    # Embedding model configuration
    EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
    COLLECTION_NAME = "fitness_knowledge"
    
    # Text splitting configuration
    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 200
    
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
        for doc in scraped_docs:
            # Create LangChain Document with metadata
            documents.append(Document(
                page_content=doc['content'],
                metadata={
                    'source': doc['url'],
                    'title': doc.get('resource_name', doc.get('title', 'Unknown')),
                    'category': doc.get('category', 'Unknown'),
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
        texts = text_splitter.split_documents(documents)
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
        k: int = 3
    ) -> List[str]:
        """
        Search for similar documents in the vector store.
        
        Args:
            query: Search query
            k: Number of results to return
            
        Returns:
            List of relevant document contents
        """
        results = self.vectorstore.similarity_search(query, k=k)
        
        # Log retrieved documents
        logger.info(f"\n{'='*70}")
        logger.info(f"📊 Vector DB Query")
        logger.info(f"{'='*70}")
        logger.info(f"Query: {query}")
        logger.info(f"Retrieved {len(results)} documents")
        
        for idx, doc in enumerate(results, 1):
            logger.info(f"\n--- Document {idx} ---")
            logger.info(f"Source: {doc.metadata.get('source', 'Unknown')}")
            logger.info(f"Title: {doc.metadata.get('title', 'Unknown')}")
            logger.info(f"Category: {doc.metadata.get('category', 'Unknown')}")
            logger.info(f"Organization: {doc.metadata.get('organization', 'Unknown')}")
            logger.info(f"Content preview: {doc.page_content[:200]}...")
        
        logger.info(f"{'='*70}\n")
        
        return [doc.page_content for doc in results]
    
    def get_context(self, query: str, k: int = 3) -> str:
        """
        Get concatenated context from similar documents.
        
        Args:
            query: Search query
            k: Number of documents to retrieve
            
        Returns:
            Concatenated context string
        """
        documents = self.similarity_search(query, k=k)
        context = "\n\n".join(documents)
        
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
