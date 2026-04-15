"""
Scrape fitness and nutrition resources from CSV and convert to embeddings.
Handles web pages, PDFs, and structured content from verified sources.
"""
import csv
import requests
import io
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # Will skip PDFs if pypdf not available
from bs4 import BeautifulSoup
import json
import time
from pathlib import Path
from typing import List, Dict, Optional
import re
from urllib.parse import urlparse
from datetime import datetime


class FitnessResourceScraper:
    """Scrape and structure fitness/nutrition content from CSV resources."""
    
    def __init__(
        self,
        csv_path: str = "resources.csv",
        output_dir: str = "data/scraped_resources"
    ):
        self.csv_path = Path(csv_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # Statistics
        self.stats = {
            'total_resources': 0,
            'successfully_scraped': 0,
            'failed': 0,
            'skipped': 0
        }
    
    def load_resources_csv(self) -> List[Dict]:
        """Load resources from CSV file."""
        resources = []
        
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                resources.append(row)
        
        self.stats['total_resources'] = len(resources)
        print(f"📄 Loaded {len(resources)} resources from CSV")
        return resources
    
    def extract_text_from_url(self, url: str, timeout: int = 15) -> Optional[str]:
        """Extract main text content from a URL."""
        try:
            response = self.session.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
                script.decompose()
            
            # Try to find main content areas
            main_content = None
            
            # Common content selectors
            content_selectors = [
                'main',
                'article',
                '[role="main"]',
                '.content',
                '.main-content',
                '#content',
                '#main',
                '.article-body',
                '.post-content'
            ]
            
            for selector in content_selectors:
                main_content = soup.select_one(selector)
                if main_content:
                    break
            
            # If no main content found, use body
            if not main_content:
                main_content = soup.find('body')
            
            if main_content:
                # Extract text
                text = main_content.get_text(separator='\n', strip=True)
                
                # Clean up text
                text = re.sub(r'\n{3,}', '\n\n', text)  # Remove excessive newlines
                text = re.sub(r' {2,}', ' ', text)  # Remove excessive spaces
                
                return text if len(text) > 100 else None
            
            return None
            
        except requests.exceptions.Timeout:
            print(f"  ⏱️ Timeout accessing {url}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"  ❌ Error accessing {url}: {e}")
            return None
        except Exception as e:
            print(f"  ⚠️ Unexpected error processing {url}: {e}")
            return None
    
    def create_document(self, resource: Dict, content: str) -> Dict:
        """Create a structured document from resource and content."""
        return {
            "id": self._generate_id(resource['URL']),
            "category": resource['Category'],
            "section": resource['Section'],
            "resource_name": resource['Resource Name'],
            "organization": resource['Organization'],
            "description": resource['Description'],
            "url": resource['URL'],
            "key_features": resource['Key Features'],
            "priority": resource['Priority'],
            "content": content,
            "content_length": len(content),
            "scraped_at": datetime.now().isoformat(),
            "metadata": {
                "domain": urlparse(resource['URL']).netloc,
                "verified": True,
                "authority": resource['Organization']
            }
        }
    
    def _generate_id(self, url: str) -> str:
        """Generate a unique ID from URL."""
        domain = urlparse(url).netloc
        path = urlparse(url).path
        return f"{domain}_{hash(path)}"[:50]
    
    def extract_text_from_pdf(self, url: str, timeout: int = 120) -> Optional[str]:
        """Extract text from a PDF URL."""
        if PdfReader is None:
            print("  ⚠️ pypdf not installed, skipping PDF")
            return None
        
        try:
            print("  📄 Downloading PDF (may take a minute for slow servers)...")
            response = self.session.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            
            # Check if the server redirected us to a Word Document instead of a PDF
            content_type = response.headers.get('Content-Type', '')
            if 'wordprocessingml.document' in content_type or url.endswith('.docx') or response.url.endswith('.docx'):
                print("  ⚠️ Server returned a Word Document (.docx) instead of a PDF. Skipping extraction.")
                return None
            
            # Read PDF from memory
            pdf_file = io.BytesIO(response.content)
            reader = PdfReader(pdf_file)
            
            print(f"  📖 Extracting text from {len(reader.pages)} pages...")
            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            
            full_text = "\n\n".join(text_parts)
            
            # Clean up text
            full_text = re.sub(r'\n{3,}', '\n\n', full_text)  # Remove excessive newlines
            full_text = re.sub(r' {2,}', ' ', full_text)  # Remove excessive spaces
            
            return full_text.strip() if full_text else None
            
        except requests.exceptions.Timeout:
            print(f"  ⏱️ Timeout downloading PDF from {url}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"  ❌ Error downloading PDF: {e}")
            return None
        except Exception as e:
            print(f"  ⚠️ Error processing PDF: {e}")
            return None
    
    def scrape_resource(self, resource: Dict) -> Optional[Dict]:
        """Scrape a single resource."""
        print(f"\n📥 Scraping: {resource['Resource Name']}")
        print(f"   URL: {resource['URL']}")
        print(f"   Organization: {resource['Organization']}")
        print(f"   Priority: {resource['Priority']}")
        
        url = resource['URL']
        
        # Check if it's a PDF
        if url.endswith('.pdf'):
            print("  📄 PDF detected - attempting extraction")
            content = self.extract_text_from_pdf(url)
            if content:
                document = self.create_document(resource, content)
                print(f"  ✅ Successfully extracted {len(content)} characters from PDF")
                self.stats['successfully_scraped'] += 1
                return document
            else:
                print(f"  ❌ Failed to extract PDF content")
                self.stats['skipped'] += 1
                return None
        
        # Extract content from web page
        content = self.extract_text_from_url(url)
        
        if content:
            document = self.create_document(resource, content)
            print(f"  ✅ Successfully extracted {len(content)} characters")
            self.stats['successfully_scraped'] += 1
            return document
        else:
            print(f"  ❌ Failed to extract content")
            self.stats['failed'] += 1
            return None
    
    def scrape_all_resources(self, max_resources: Optional[int] = None, priority_filter: Optional[str] = 'HIGH') -> List[Dict]:
        """Scrape all resources from CSV.
        
        Args:
            max_resources: Maximum number of resources to process (None = all)
            priority_filter: Priority level to scrape ('HIGH', 'MEDIUM', or None for all)
        """
        resources = self.load_resources_csv()
        
        if max_resources:
            resources = resources[:max_resources]
            print(f"⚠️ Limited to first {max_resources} resources for testing\n")
        
        documents = []
        
        for idx, resource in enumerate(resources, 1):
            print(f"\n{'='*60}")
            print(f"Progress: {idx}/{len(resources)}")
            print(f"{'='*60}")
            
            # Filter by priority if specified
            if priority_filter and resource['Priority'] != priority_filter:
                print(f"⏭️ Skipping {resource['Resource Name']} (Priority: {resource['Priority']})")
                self.stats['skipped'] += 1
                continue
            
            document = self.scrape_resource(resource)
            
            if document:
                documents.append(document)
            
            # Be respectful to servers - rate limiting
            time.sleep(3)
        
        return documents
    
    def save_documents(self, documents: List[Dict], filename: str = "scraped_documents.json"):
        """Save documents to JSON file."""
        output_path = self.output_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(documents, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Saved {len(documents)} documents to {output_path}")
    
    def create_summary(self, documents: List[Dict]) -> Dict:
        """Create summary statistics."""
        summary = {
            "scraping_completed_at": datetime.now().isoformat(),
            "statistics": self.stats,
            "documents_created": len(documents),
            "total_content_length": sum(doc['content_length'] for doc in documents),
            "categories": {},
            "organizations": {}
        }
        
        # Count by category
        for doc in documents:
            cat = doc['category']
            summary['categories'][cat] = summary['categories'].get(cat, 0) + 1
        
        # Count by organization
        for doc in documents:
            org = doc['organization']
            summary['organizations'][org] = summary['organizations'].get(org, 0) + 1
        
        return summary
    
    def print_summary(self, summary: Dict):
        """Print scraping summary."""
        print("\n" + "="*60)
        print("📊 SCRAPING SUMMARY")
        print("="*60)
        print(f"\n📈 Statistics:")
        print(f"  Total resources: {summary['statistics']['total_resources']}")
        print(f"  Successfully scraped: {summary['statistics']['successfully_scraped']}")
        print(f"  Failed: {summary['statistics']['failed']}")
        print(f"  Skipped: {summary['statistics']['skipped']}")
        print(f"\n📄 Documents created: {summary['documents_created']}")
        print(f"📝 Total content length: {summary['total_content_length']:,} characters")
        
        print(f"\n📚 By Category:")
        for cat, count in summary['categories'].items():
            print(f"  {cat}: {count}")
        
        print(f"\n🏛️ By Organization:")
        for org, count in summary['organizations'].items():
            print(f"  {org}: {count}")
        
        print("\n" + "="*60)
    
    def run(self, max_resources: Optional[int] = None, priority_filter: Optional[str] = 'HIGH'):
        """Run the complete scraping process.
        
        Args:
            max_resources: Maximum number of resources to process
            priority_filter: Priority level to scrape ('HIGH', 'MEDIUM', or None for all)
        """
        print("="*60)
        print("🏋️ FitMind AI Coach - Resource Scraper")
        print("="*60)
        
        # Scrape all resources
        documents = self.scrape_all_resources(max_resources=max_resources, priority_filter=priority_filter)
        
        # Save documents
        if documents:
            self.save_documents(documents)
            
            # Create and save summary
            summary = self.create_summary(documents)
            self.save_documents([summary], "scraping_summary.json")
            self.print_summary(summary)
        else:
            print("\n⚠️ No documents were successfully scraped!")
        
        return documents


if __name__ == "__main__":
    import sys
    
    # Usage: python scrape_fitness_resources.py [max_resources] [priority_filter]
    # Examples:
    #   python scrape_fitness_resources.py 5           # First 5 HIGH priority
    #   python scrape_fitness_resources.py 999 HIGH    # All HIGH priority
    #   python scrape_fitness_resources.py 999 ALL     # All resources
    max_resources = int(sys.argv[1]) if len(sys.argv) > 1 else None
    priority_arg = sys.argv[2].upper() if len(sys.argv) > 2 else 'HIGH'
    priority_filter = None if priority_arg == 'ALL' else priority_arg
    
    scraper = FitnessResourceScraper(
        csv_path="resources.csv",
        output_dir="data/scraped_resources"
    )
    
    documents = scraper.run(max_resources=max_resources, priority_filter=priority_filter)
    
    print(f"\n✅ Scraping complete! Next step: convert to embeddings with load_to_vectordb.py")
