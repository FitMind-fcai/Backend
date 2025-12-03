import os
from typing import List, Optional
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings


class VectorDBService:
    
    # Default paths
    BASE_DIR = os.path.dirname(__file__)
    DEFAULT_PERSIST_DIR = os.path.join(BASE_DIR, "chroma_db")
    DEFAULT_PDF_PATH = os.path.join(BASE_DIR, "fitness-handbook.pdf")
    
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
    
    def create_vector_db(
        self,
        pdf_path: Optional[str] = None,
        force_recreate: bool = False
    ) -> dict:
        """
        Create the vector database from a PDF file.
        
        Args:
            pdf_path: Path to the PDF file to process
            force_recreate: If True, recreate even if DB exists
            
        Returns:
            Dictionary with creation statistics
        """
        pdf_path = pdf_path or self.DEFAULT_PDF_PATH
        
        # Check if database already exists
        if os.path.exists(self.persist_directory) and not force_recreate:
            return {
                "status": "exists",
                "message": f"Vector database already exists at {self.persist_directory}",
                "persist_directory": self.persist_directory
            }
        
        # Validate PDF path
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found at {pdf_path}")
        
        # Load PDF
        print(f"📄 Loading PDF file: {pdf_path}")
        loader = PyPDFLoader(pdf_path)
        documents = loader.load()
        print(f"✓ Loaded {len(documents)} pages from PDF")
        
        # Split documents into chunks
        print("✂️ Splitting documents into chunks...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.CHUNK_SIZE,
            chunk_overlap=self.CHUNK_OVERLAP,
            separators=["\n\n", "\n", " ", ""]
        )
        texts = text_splitter.split_documents(documents)
        print(f"📝 Created {len(texts)} text chunks from PDF")
        
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
            "pages_loaded": len(documents),
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
        return "\n\n".join(documents)
    
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


def initialize_vector_db(force_recreate: bool = False) -> dict:
    """
    Initialize the vector database.
    This should be called once during application setup.
    
    Args:
        force_recreate: If True, recreate even if DB exists
        
    Returns:
        Dictionary with initialization status
    """
    service = get_vector_db_service()
    return service.create_vector_db(force_recreate=force_recreate)


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
