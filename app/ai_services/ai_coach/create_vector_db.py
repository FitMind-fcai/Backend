import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings

# Directory where Chroma will store its data
PERSIST_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")

# Load PDF file
print("📄 Loading PDF file...")
pdf_path = os.path.join(os.path.dirname(__file__), "fitness-handbook.pdf")
loader = PyPDFLoader(pdf_path)
documents = loader.load()

print(f"✓ Loaded {len(documents)} pages from PDF")
print(f"First page preview: {documents[0].page_content[:200]}...\n")

# Split documents into chunks
print("✂️ Splitting documents into chunks...")
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    separators=["\n\n", "\n", " ", ""]
)
texts = text_splitter.split_documents(documents)

print(f"📝 Created {len(texts)} text chunks from PDF")

# Embedding model
embeddings = HuggingFaceEmbeddings(model_name='all-MiniLM-L6-v2')

# Create persistent vectorstore
print("🔧 Creating and saving vector store...")
vectorstore = Chroma.from_documents(
    documents=texts,
    embedding=embeddings,
    collection_name="fitness_test",
    persist_directory=PERSIST_DIR
)

# No need to call persist() - it's automatic with persist_directory
print(f"✅ Vector store saved in: {PERSIST_DIR}")