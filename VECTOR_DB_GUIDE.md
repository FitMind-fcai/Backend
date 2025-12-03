# 🏋️ Vector Database Setup & Usage Guide

## 📚 Overview

The AI Coach uses **Retrieval-Augmented Generation (RAG)** with a vector database to provide evidence-based fitness and nutrition advice from trusted sources like ACSM, NSCA, WHO, and USDA.

**Key Concept:** Build once → Use forever → Rebuild when adding new content

---

## 🔄 Vector DB Lifecycle

### **Phase 1: BUILD (One-Time Setup)**

```
resources.csv (28 sources)
    ↓
📥 Scraper extracts content from websites & PDFs
    ↓
data/scraped_resources/scraped_documents.json
    ↓
✂️  Split into 1000-char chunks (200 overlap)
    ↓
🧠 Generate embeddings (HuggingFace all-MiniLM-L6-v2)
    ↓
💾 Store in ChromaDB → app/ai_services/ai_coach/chroma_db/
    ↓
✅ Database persisted to disk (ready to use!)
```

### **Phase 2: LOAD (On First API Request)**

```
FastAPI starts → AI Coach initializes
    ↓
First request arrives
    ↓
VectorDBService.vectorstore property accessed
    ↓
Load ChromaDB from disk (~1 second)
    ↓
Database stays in memory for all future requests
```

### **Phase 3: USE (Every Request)**

```
User: "Create workout plan"
    ↓
AI Coach builds query: "workout plan Strength Training Intermediate Gym injuries: knee pain"
    ↓
VectorDBService.similarity_search(query, k=5)
    ↓
Returns 5 most relevant chunks from ACSM/NSCA/etc
    ↓
AI Coach includes context in LLM prompt
    ↓
LLM generates personalized plan using verified knowledge
```

**Performance:**
- Load from disk: < 1 second (first request only)
- Similarity search: < 100ms per query
- No re-embedding needed!

---

## 🚀 How to Build Vector Database

### **Option 1: Docker Container (Recommended)**

```powershell
# From Backend directory
docker-compose exec web python scripts/setup_vector_db.py
```

**Choose scraping option:**
- `1` - Test mode (3 resources, ~1 minute)
- `2` - High priority (17 HIGH resources, ~5 minutes) **← Recommended**
- `3` - All resources (28 total including MEDIUM, ~10 minutes)

The script will:
1. Check dependencies
2. Scrape fitness resources from web + PDFs
3. Generate embeddings
4. Create ChromaDB at `app/ai_services/ai_coach/chroma_db/`
5. Run test queries

### **Option 2: Local Environment**

```powershell
# Ensure dependencies installed
pip install beautifulsoup4 requests pypdf langchain langchain-community chromadb sentence-transformers

# Run setup script
python scripts/setup_vector_db.py
```

### **Option 3: Manual Step-by-Step**

```powershell
# Step 1: Scrape resources
python scripts/scrape_fitness_resources.py 999 HIGH
# Output: data/scraped_resources/scraped_documents.json

# Step 2: Create vector database
python -c "from app.ai_services.ai_coach.vector_db_service import initialize_vector_db; initialize_vector_db(force_recreate=True)"
# Output: app/ai_services/ai_coach/chroma_db/
```

---

## 🔍 How It Works in Your Application

### **1. Initialization (First Request)**

```python
# app/ai_services/ai_coach/ai_coach_service.py
class AICoachService:
    def __init__(self):
        # Gets singleton VectorDBService
        self.vector_db = get_vector_db_service()
        
    # First time .vectorstore is accessed:
    @property
    def vectorstore(self):
        if self._vectorstore is None:
            self._vectorstore = self._load_vectorstore()  # Loads from disk
        return self._vectorstore
```

### **2. Workout Plan Generation**

```python
def generate_workout_plan(self, user_profile, preferences):
    # Build context-aware query
    query = f"workout plan {preferences.workout_focus} {preferences.workout_difficulty}"
    if user_profile.injuries:
        query += f" injuries: {user_profile.injuries}"
    if user_profile.medical_conditions:
        query += f" medical conditions: {user_profile.medical_conditions}"
    
    # Retrieve relevant knowledge (k=5 chunks)
    rag_context = self.vector_db.get_context(query, k=5)
    
    # Include in LLM prompt
    prompt = f"""
    REFERENCE FITNESS KNOWLEDGE:
    {rag_context}
    
    USER PROFILE:
    {user_profile.to_context_string()}
    
    Generate a workout plan...
    """
```

**Example Retrieved Context:**
```
Document 1: NSCA Strength Training
"Progressive overload requires increasing training load by 2-10% 
when current weight becomes manageable for 2+ reps above target..."

Document 2: ACSM Exercise Guidelines
"For knee injuries, avoid deep squats. Recommended alternatives:
- Partial squats (45-90° knee flexion)
- Leg press with controlled ROM..."

Document 3: ExRx Exercise Database
"Intermediate strength training frequency: 3-4 sessions per week
with 48-72 hours recovery between muscle groups..."
```

### **3. Nutrition Plan Generation**

```python
def generate_nutrition_plan(self, user_profile, preferences):
    # Build context-aware query
    query = f"nutrition meal plan {preferences.cuisine_preference}"
    if user_profile.allergies:
        query += f" allergies: {user_profile.allergies}"
    if user_profile.medical_conditions:
        query += f" medical conditions: {user_profile.medical_conditions}"
    
    # Retrieve relevant nutrition knowledge
    rag_context = self.vector_db.get_context(query, k=5)
```

### **4. Ask Coach Endpoint**

```python
def ask_coach(self, question, user_profile=None):
    # Enhance query with user profile
    query = question
    if user_profile and user_profile.injuries:
        query += f" injuries: {user_profile.injuries}"
    
    # Get relevant context
    rag_context = self.vector_db.get_context(query, k=3)
    
    # LLM generates response using context
```

---

## 📊 Logging & Debugging

Logs are written to console and `logs/fitmind.log`:

```
2025-12-04 10:30:15 - vector_db_service - INFO - 
======================================================================
📊 Vector DB Query
======================================================================
Query: workout plan Strength Training Intermediate Gym injuries: knee pain
Retrieved 5 documents

--- Document 1 ---
Source: https://www.nsca.com/education/tools-and-resources/
Title: NSCA Basics of Strength and Conditioning Manual
Category: Exercise Programming & Fitness Guidelines
Organization: National Strength & Conditioning Association
Content preview: Comprehensive strength training guide...

📝 Total context length: 15420 characters
```

**To view logs:**
```powershell
# Docker logs
docker-compose logs -f web

# Or check file
cat logs/fitmind.log
```

---

## 📂 Data Sources

**resources.csv** contains 28 curated resources:

| Category             | Count | Examples                                |
| -------------------- | ----- | --------------------------------------- |
| Exercise Programming | 7     | ACSM, NSCA, ExRx.net                    |
| Nutrition Guidelines | 4     | WHO, USDA FoodData Central              |
| Sports Nutrition     | 4     | ISSN Position Stands                    |
| Exercise Database    | 4     | ExRx.net (2,100+ exercises)             |
| Periodization        | 3     | NASM, Linear/Block/Undulating           |
| TDEE Calculators     | 3     | Calculator.net, TDEE Calculator         |
| Fitness Books (PDFs) | 2     | Army ROTC Handbook, Fitness for Dummies |

**Priority Levels:**
- `HIGH` (17 resources): Core evidence-based guidelines - **Recommended**
- `MEDIUM` (11 resources): Additional calculators and guides

---

## 🔄 When to Rebuild

### **Rebuild Required:**
✅ First time setup  
✅ Added new URLs to `resources.csv`  
✅ Updated existing resources  
✅ Changed chunking parameters (CHUNK_SIZE, CHUNK_OVERLAP)  

### **Rebuild NOT Required:**
❌ Server restart  
❌ Container restart  
❌ Code changes to AI Coach service  
❌ Every API request  

### **How to Rebuild:**

```powershell
# Docker
docker-compose exec web python scripts/setup_vector_db.py

# Choose option 2 (HIGH priority) or 3 (ALL resources)
```

The script uses `force_recreate=True` which automatically deletes the old database and creates a fresh one.

---

## 🎯 Technical Details

### **Embedding Model**
- **Model:** `all-MiniLM-L6-v2` (HuggingFace)
- **Dimensions:** 384
- **Size:** ~90MB (downloads once)
- **Speed:** ~1000 embeddings/second

### **Text Chunking**
```python
RecursiveCharacterTextSplitter(
    chunk_size=1000,        # Characters per chunk
    chunk_overlap=200,      # Overlap to preserve context
    separators=["\n\n", "\n", " ", ""]
)
```

### **Database Stats (HIGH priority)**
- **Resources:** 17 sources
- **Raw content:** ~1.4 million characters
- **Text chunks:** ~1,944 chunks
- **Disk size:** ~100-150MB
- **Query time:** < 100ms

### **Similarity Search**
- **Algorithm:** Cosine similarity on vector embeddings
- **Default k:** 3-5 documents retrieved
- **Metadata:** Preserved (source URL, title, category, organization)

---

## 🐛 Troubleshooting

### **"Vector database not found"**
```
FileNotFoundError: Vector database not found at app/ai_services/ai_coach/chroma_db/
```
**Solution:** Run `python scripts/setup_vector_db.py`

### **"Scraped documents not found"**
```
FileNotFoundError: Scraped documents not found at data/scraped_resources/scraped_documents.json
```
**Solution:** Run scraper first: `python scripts/scrape_fitness_resources.py 999 HIGH`

### **"Failed to send telemetry event"**
```
Failed to send telemetry event ClientStartEvent: capture() takes 1 positional argument but 3 were given
```
**Status:** Harmless ChromaDB telemetry warning - database works fine

### **"404 Error" or "403 Forbidden" during scraping**
Some URLs may fail (PDFs moved, sites block scrapers). This is normal - the script continues with successful scrapes.

**Fix broken URLs:**
1. Find working alternatives
2. Update `resources.csv`
3. Rebuild: `python scripts/setup_vector_db.py`

### **CSV parsing errors**
```
Priority: testing standards  ← Should be "HIGH"
```
**Cause:** Commas in "Key Features" column breaking CSV parsing  
**Solution:** Wrap fields with commas in quotes: `"testing standards, protocols"`

---

## 📈 Performance Optimization

### **Current Setup (Optimized)**
- ✅ Lazy loading (database loaded only when needed)
- ✅ Singleton pattern (one instance shared across requests)
- ✅ Persistent storage (no rebuilding on restart)
- ✅ Fast similarity search (< 100ms)

### **If You Need Faster Cold Start**
Preload database on server startup:
```python
# main.py
@app.on_event("startup")
def startup_event():
    from app.ai_services.ai_coach.vector_db_service import get_vector_db_service
    db = get_vector_db_service()
    _ = db.vectorstore  # Force load during startup
    print("✅ Vector database preloaded")
```

---

## 🎉 Quick Start Checklist

- [ ] Ensure Docker container running: `docker-compose up -d`
- [ ] Run setup: `docker-compose exec web python scripts/setup_vector_db.py`
- [ ] Choose option `2` (HIGH priority, 17 resources)
- [ ] Wait ~5 minutes for completion
- [ ] Verify: `ls app/ai_services/ai_coach/chroma_db/` shows files
- [ ] Test: Generate a workout plan via API
- [ ] Check logs: `docker-compose logs -f web` to see RAG queries

**Done!** Your AI Coach now uses evidence-based knowledge from trusted fitness organizations.

---

## 📖 Related Documentation

- **Scraping Details:** `scripts/README_SCRAPING.md`
- **Vector DB Code:** `app/ai_services/ai_coach/vector_db_service.py`
- **AI Coach Service:** `app/ai_services/ai_coach/ai_coach_service.py`
- **Resources List:** `resources.csv`

---

**Summary:** Build once with `setup_vector_db.py` → Database persists → Loads automatically on first request → Queries return relevant knowledge → AI generates better plans!
