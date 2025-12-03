"""
Master runner for setting up the vector database.
Run this ONCE to scrape resources and build the vector DB.

This script:
1. Checks dependencies
2. Scrapes resources from CSV
3. Uses VectorDBService to create embeddings and ChromaDB

One-time setup - database persists forever!
"""
import subprocess
import sys
from pathlib import Path

# Add parent to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_command(command: str, description: str) -> bool:
    """Run a command and handle errors."""
    print("\n" + "="*70)
    print(f"▶️  {description}")
    print("="*70)
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=False,
            text=True
        )
        print(f"✅ {description} - SUCCESS")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} - FAILED")
        print(f"Error: {e}")
        return False


def check_dependencies():
    """Check if required packages are installed."""
    print("\n" + "="*70)
    print("🔍 Checking dependencies...")
    print("="*70)
    
    # Map of package names to their import names
    required_packages = {
        'beautifulsoup4': 'bs4',
        'requests': 'requests',
        'langchain': 'langchain',
        'langchain-community': 'langchain_community',
        'chromadb': 'chromadb',
        'sentence-transformers': 'sentence_transformers'
    }
    
    missing = []
    for package, import_name in required_packages.items():
        try:
            __import__(import_name)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package} - NOT INSTALLED")
            missing.append(package)
    
    if missing:
        print(f"\n⚠️  Missing packages: {', '.join(missing)}")
        print(f"\nInstall with:")
        print(f"pip install {' '.join(missing)}")
        return False
    
    print("\n✅ All dependencies installed!")
    return True


def main():
    """Main setup workflow."""
    print("="*70)
    print("🏋️  FitMind AI Coach - Vector Database Setup")
    print("="*70)
    print("\nThis script will:")
    print("1. Check dependencies")
    print("2. Scrape fitness resources from CSV")
    print("3. Convert to embeddings and store in ChromaDB")
    print("\n⏱️  Estimated time: 5-10 minutes")
    print("\n" + "="*70)
    
    # Check if user wants to continue
    response = input("\nContinue? (y/n): ").lower()
    if response != 'y':
        print("Setup cancelled.")
        return
    
    # Step 1: Check dependencies
    if not check_dependencies():
        print("\n❌ Please install missing dependencies first.")
        sys.exit(1)
    
    # Step 2: Ask how many resources to scrape
    print("\n" + "="*70)
    print("📊 Scraping Options")
    print("="*70)
    print("1. Test mode (3 resources) - Quick test")
    print("2. High priority (17 HIGH resources) - Recommended")
    print("3. All resources (28 resources, includes MEDIUM) - Complete but slow")
    
    choice = input("\nChoose option (1/2/3) [default: 2]: ").strip() or "2"
    
    scraper_options = {
        "1": ("3", "HIGH"),
        "2": ("999", "HIGH"),  # All HIGH priority resources
        "3": ("999", "ALL")     # All resources regardless of priority
    }
    max_resources, priority_filter = scraper_options.get(choice, ("999", "HIGH"))
    
    # Step 3: Run scraper
    scraper_cmd = f"python scripts/scrape_fitness_resources.py {max_resources} {priority_filter}"
    if not run_command(scraper_cmd, "Scraping fitness resources"):
        print("\n❌ Scraping failed. Check your internet connection.")
        sys.exit(1)
    
    # Step 4: Check if we have scraped data
    scraped_file = Path("data/scraped_resources/scraped_documents.json")
    if not scraped_file.exists():
        print("\n❌ No scraped documents found. Scraping may have failed.")
        sys.exit(1)
    
    # Step 5: Load into vector database using VectorDBService
    print("\n" + "="*70)
    print("▶️  Loading into vector database")
    print("="*70)
    
    try:
        from app.ai_services.ai_coach.vector_db_service import initialize_vector_db
        
        result = initialize_vector_db(
            source_path=str(scraped_file),
            source_type="scraped",
            force_recreate=True
        )
        
        print("\n📊 Vector Database Result:")
        for key, value in result.items():
            print(f"  {key}: {value}")
        
        print(f"\n✅ Loading into vector database - SUCCESS")
        
    except Exception as e:
        print(f"\n❌ Loading into vector database - FAILED")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Step 6: Verify vector DB exists
    vector_db_path = Path("app/ai_services/ai_coach/chroma_db")
    if not vector_db_path.exists():
        print("\n❌ Vector database not created at expected location.")
        sys.exit(1)
    
    # Success!
    print("\n" + "="*70)
    print("🎉 SETUP COMPLETE!")
    print("="*70)
    print(f"\n✅ Vector database created at: {vector_db_path}")
    print(f"✅ Your AI Coach is now ready to use!")
    print("\n📝 Next steps:")
    print("   1. Start your FastAPI server: uvicorn main:app --reload")
    print("   2. The AI Coach will automatically load the vector DB")
    print("   3. Generate plans - they'll include verified knowledge!")
    print("\n💡 The vector DB is persistent - no need to rebuild unless:")
    print("   - You add new resources to resources.csv")
    print("   - You want to update existing content")
    print("="*70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Setup interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        sys.exit(1)
