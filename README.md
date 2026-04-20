# FitMind Backend API

A FastAPI backend for the FitMind fitness application — featuring AI-powered workout & nutrition plan generation, meal scanning, voice transcription, user authentication (JWT + OTP), health profile management, and a RAG-based AI coach backed by ChromaDB.

---

## Table of Contents

1. [Tech Stack](#tech-stack)
2. [Project Structure](#project-structure)
3. [Architecture](#architecture)
4. [API Versioning](#api-versioning)
5. [Module Overview](#module-overview)
6. [Authentication Flow](#authentication-flow)
7. [Environment Variables](#environment-variables)
8. [Local Development Setup](#local-development-setup)
9. [Docker Setup](#docker-setup)
10. [Deployment (Railway)](#deployment-railway)
11. [Vector Database (RAG / AI Coach)](#vector-database-rag--ai-coach)
12. [Scripts (Linux & Windows)](#scripts-linux--windows)
13. [AI Coach Evaluation (LLM-as-Judge)](#ai-coach-evaluation-llm-as-judge)
14. [Development Guidelines](#development-guidelines)
15. [Troubleshooting](#troubleshooting)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI |
| Database | PostgreSQL 16 (SQLAlchemy ORM) |
| Cache / OTP Store | Redis 7 |
| Authentication | JWT + bcrypt |
| AI / LLM | Groq API (Llama, Mixtral, Whisper) |
| Vector DB | ChromaDB + HuggingFace `BAAI/bge-small-en-v1.5` |
| Validation | Pydantic v2 |
| Containerization | Docker + Docker Compose |
| Docs | Auto-generated Swagger / ReDoc |

---

## Project Structure

```
Backend/
├── main.py                          # App entrypoint, router registration
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env                             # Local env vars (never commit)
├── .env.example                     # Template for new team members
├── resources.csv                    # RAG data sources (28 fitness resources)
├── scripts/
│   ├── scrape_fitness_resources.py  # Scrapes resources.csv sources
│   ├── setup_vector_db.py           # Builds ChromaDB vector store
│   ├── import_food.py               # Imports nutrition.csv into central_foods
│   ├── import_workouts.py           # Imports megaGymDataset.csv into central_exercises
│   └── evaluate_rag_pipeline.py     # LLM-as-judge evaluation runner
├── data/
│   └── scraped_resources/
│       └── scraped_documents.json
└── app/
    ├── core/                        # Global config, security, Redis client
    ├── db/                          # SQLAlchemy engine & session
    ├── shared/                      # Base repository, shared email service
    ├── ai_services/                 # AI integrations (Groq wrappers)
    │   ├── ai_coach/                # RAG-based plan generation
    │   ├── evaluation/              # LLM-as-judge evaluation pipeline
    │   ├── meal_scanner/            # Food image analysis
    │   └── voice_transcriber/       # Audio → structured data
    ├── auth_module/                 # Registration, login, OTP, JWT
    ├── profile_module/              # Health profiles, BMR/TDEE
    ├── planning_module/             # Workout & nutrition plans
    ├── tracking_module/             # Progress logging (planned)
    ├── chatbot_module/              # Conversational AI coach (planned)
    └── notification_module/         # Push notifications (planned)
```

---

## Architecture

### Layered Module Pattern

Every module follows the same structure:

```
module/
├── models/        → SQLAlchemy DB entities
├── repositories/  → Data access layer (DB queries)
├── services/      → Business logic
├── routes/        → FastAPI route handlers (thin, delegates to services)
└── schemas/       → Pydantic request/response models
```

**Request flow:**
```
HTTP Request → Route → Service → Repository → Database
                           ↓
                     AI Service (when needed)
```

### Re-Export Pattern

Module-specific `core/` folders re-export from `app/core` and add module-specific extensions:

```python
# auth_module/core/security.py
from app.core.security import hash_password, verify_password  # re-export
def generate_otp(): ...           # auth-specific extension
def generate_verification_token(): ...
```

### Dependency Injection

All services are wired via FastAPI `Depends()`:

```python
@router.post("/register")
def register(
    user_data: UserCreate,
    auth_service: AuthService = Depends(get_auth_service)
):
    return auth_service.create_user(user_data)
```

### Key Design Decisions

| Decision | Reason |
|---|---|
| Monolithic (for now) | Faster dev, simpler deploy, good for GP/MVP |
| External AI APIs (Groq) | No GPU infra needed, cost-effective, latest models |
| Synchronous routes | Simpler code, SQLAlchemy ORM is sync |
| Redis for OTPs & tokens | Auto-expiry via TTL, atomic counters, no DB migrations |
| JSON preferences in plan | Enables history/regeneration without extra tables |
| Deterministic food retrieval for AI plans | Avoids random ingredient sets and improves semantic consistency |
| Hybrid RAG retrieval with metadata-aware context blocks | Improves relevance and grounding vs plain vector search |
| Source-quality filtering before embedding | Reduces navigation/boilerplate noise in retrieved context |

---

## API Versioning

All endpoints are versioned under `/v1`. The base URL pattern is:

```
https://app.fitmind.ai/v1/{module}/{endpoint}
```

| Module | Base Path |
|---|---|
| Authentication | `/v1/auth/...` |
| Profiles | `/v1/profiles/...` |
| Plan Generation | `/v1/plans/...` |
| Workout Plans | `/v1/workout-plans/...` |
| Nutrition Plans | `/v1/nutrition-plans/...` |

**Interactive Docs:**
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

To add a future v2, simply create a new `APIRouter(prefix="/v2")` in `main.py` and include the upgraded routers.

---

## Module Overview

| Module | Status | Endpoints |
|---|---|---|
| `auth_module` | ✅ Complete | Register, login, verify email, OTP password reset |
| `profile_module` | ✅ Complete | Create/get/update health profile, BMR/TDEE |
| `planning_module` | 🟡 In Progress | Generate, get, and list workout & nutrition plans |
| `ai_services` | 🟡 In Progress | AI coach, meal scanner, voice transcriber |
| `tracking_module` | ⏳ Planned | Workout/meal/weight logging |
| `chatbot_module` | ⏳ Planned | Conversational AI coach |
| `notification_module` | ⏳ Planned | Push notifications & reminders |

### Auth Endpoints (`/v1/auth`)

| Method | Path | Description |
|---|---|---|
| POST | `/signup` | Register new user |
| POST | `/login` | Authenticate, returns JWT |
| GET | `/verify-email?token=...` | Verify email via token |
| POST | `/resend-verification` | Resend verification email |
| GET | `/me` | Get current user (requires JWT) |
| POST | `/forgot-password` | Request OTP for password reset |
| POST | `/verify-reset-otp` | Validate OTP |
| POST | `/reset-password` | Set new password |

### Profile Endpoints (`/v1/profiles`)

| Method | Path | Description |
|---|---|---|
| POST | `/` | Create health profile |
| GET | `/me` | Get current user's profile |
| PUT | `/me` | Update profile |

---

## Authentication Flow

### Signup & Email Verification
```
POST /v1/auth/signup
    → creates user (is_verified=False)
    → stores verify:{token} → email in Redis (TTL 24h)
    → sends email: https://app.fitmind.ai/v1/auth/verify-email?token=...

GET /v1/auth/verify-email?token=...
    → reads email from Redis
    → sets is_verified=True in DB
    → deletes token from Redis
```

### Login
```
POST /v1/auth/login
    → verifies password (bcrypt)
    → checks is_verified=True
    → returns signed JWT (24h expiry)
```

### Password Reset
```
POST /v1/auth/forgot-password
    → generates OTP
    → stores hashed OTP in Redis (TTL 10min)
    → emails OTP to user

POST /v1/auth/verify-otp
    → validates OTP against Redis hash
    → tracks failed attempts (max 4)

POST /v1/auth/reset-password
    → re-validates OTP
    → updates password in DB
    → deletes OTP keys from Redis
```

### Redis Key Structure

```
otp:{email}               → hashed OTP          (TTL 10 min)
otp_attempts:{email}      → failed count         (TTL 10 min)
otp_cooldown:{email}      → resend cooldown       (TTL 2 min)
otp_hourly:{email}        → hourly request count  (TTL 1 hr)
otp_daily:{email}         → daily request count   (TTL 24 hr)
otp_blocked:{email}       → block flag            (TTL variable)
verify:{token}            → email address         (TTL 24 hr)
```

### Protecting Routes

```python
from app.core.dependencies import get_current_user, get_verified_user

@router.get("/protected")
def protected(user = Depends(get_current_user)):   # JWT required
    ...

@router.get("/premium")
def premium(user = Depends(get_verified_user)):    # JWT + email verified
    ...
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

### Complete Variable Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | ✅ | — | PostgreSQL connection string |
| `REDIS_HOST` | ✅ | `localhost` | Redis hostname |
| `REDIS_PORT` | ✅ | `6379` | Redis port |
| `REDIS_PASSWORD` | — | — | Redis password (if set) |
| `JWT_SECRET_KEY` | ✅ | — | JWT signing secret — **app will not start without this** |
| `SMTP_SERVER` | ✅ | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | ✅ | `587` | SMTP port |
| `SENDER_EMAIL` | ✅ | — | Email address for sending |
| `SENDER_PASSWORD` | ✅ | — | Gmail app password |
| `APP_URL` | ✅ | `http://localhost:8000` | Base URL (used in verification emails) |
| `GROQ_API_KEY` | ✅ | — | Groq API key (`gsk_...`) |
| `VECTOR_DB_PATH` | — | `chroma_db` | Path to ChromaDB store |
| `AI_MODEL_NAME` | — | `mixtral-8x7b-32768` | LLM model |
| `AI_EMBEDDING_MODEL` | — | `all-MiniLM-L6-v2` | Embedding model |
| `AI_VECTOR_COLLECTION_NAME` | — | `fitness_knowledge` | ChromaDB collection |
| `AI_TEMPERATURE_WORKOUT` | — | `0.3` | LLM temperature for workout plans |
| `AI_TEMPERATURE_NUTRITION` | — | `0.4` | LLM temperature for nutrition plans |
| `AI_TEMPERATURE_SUGGESTIONS` | — | `0.7` | LLM temperature for suggestions |
| `AI_MAX_TOKENS_PLANS` | — | `4000` | Max tokens for plan generation |
| `AI_MAX_TOKENS_SUGGESTIONS` | — | `800` | Max tokens for suggestions |
| `AI_RAG_TOP_K` | — | `3` | Number of RAG chunks retrieved |
| `ENVIRONMENT` | — | `development` | `development` or `production` |

**Generate a strong JWT secret:**
```bash
openssl rand -hex 32
```

> **Security:** `.env` is in `.gitignore`. Never commit it. All sensitive values are read exclusively from environment variables — no secrets are hardcoded in source code.

---

## Local Development Setup

### Prerequisites
- Python 3.13+
- PostgreSQL 16+
- Redis 7+

### Steps

```bash
# 1. Clone the repo
git clone <repo-url>
cd Backend

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your local database/redis credentials

# 5. Create the database
psql -U postgres -c "CREATE DATABASE fastapi_db;"

# 6. Run the application
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at: `http://localhost:8000/docs`

---

## Docker Setup

Docker Compose orchestrates three services: `db` (PostgreSQL), `redis`, and `web` (FastAPI).

### Quick Start

```bash
# Build and start all services
docker-compose up --build

# Run in background
docker-compose up -d --build

# Stop services
docker-compose down

# Stop and wipe all data (volumes)
docker-compose down -v
```

### Useful Commands

```bash
# View logs (all services)
docker-compose logs -f

# View only app logs
docker-compose logs -f web

# Access PostgreSQL
docker exec -it FitMind_DB psql -U postgres -d fastapi_db

# Access Redis CLI
docker exec -it FitMind_Redis redis-cli

# Rebuild after code changes
docker-compose up --build
```

### Services & Ports

| Service | Container | Port |
|---|---|---|
| FastAPI app | `FitMind_APIs` | `8000` |
| PostgreSQL | `FitMind_DB` | `5432` |
| Redis | `FitMind_Redis` | `6379` |

---

## Deployment (Railway)

### 1. Push to GitHub
```bash
git add .
git commit -m "feat: your feature"
git push origin main
```

### 2. Create Railway Project
1. Go to [railway.app](https://railway.app) → sign in with GitHub
2. **New Project** → **Deploy from GitHub repo** → select this repo
3. Add **PostgreSQL** plugin: New → Database → PostgreSQL
4. Add **Redis** plugin: New → Database → Redis

### 3. Set Service Variables
In your Railway service → **Variables** tab:

```
JWT_SECRET_KEY         = <generate: openssl rand -hex 32>
SMTP_SERVER            = smtp.gmail.com
SMTP_PORT              = 587
SENDER_EMAIL           = fitmind.dev.fcai@gmail.com
SENDER_PASSWORD        = <gmail app password>
APP_URL                = https://your-app.up.railway.app
GROQ_API_KEY           = gsk_...
VECTOR_DB_PATH         = chroma_db
AI_MODEL_NAME          = mixtral-8x7b-32768
AI_EMBEDDING_MODEL     = all-MiniLM-L6-v2
AI_VECTOR_COLLECTION_NAME = fitness_knowledge
ENVIRONMENT            = production
```

Railway auto-injects `DATABASE_URL` from the PostgreSQL plugin. For Redis, reference plugin variables:
```
REDIS_HOST     = ${{Redis.REDIS_HOST}}
REDIS_PORT     = ${{Redis.REDIS_PORT}}
REDIS_PASSWORD = ${{Redis.REDIS_PASSWORD}}
```

### 4. Custom Domain (optional)
**Settings → Networking → Custom Domain** → enter `app.fitmind.ai`  
Then add a `CNAME` DNS record: `app.fitmind.ai` → Railway-provided domain.

Railway auto-deploys on every `git push` to `main`.

---

## Vector Database (RAG / AI Coach)

The AI Coach uses **Retrieval-Augmented Generation (RAG)** with ChromaDB to ground responses with evidence from ACSM, NSCA, WHO, USDA and 25+ other trusted sources.

### How It Works

```
resources.csv (28 sources)
    ↓ scraper
data/scraped_resources/scraped_documents.json
    ↓ quality filter (drop low-signal boilerplate/navigation-heavy pages)
    ↓ cleaner + chunker (~2200 chars, 200 overlap)
    ↓ metadata enrichment (chunk_summary + chunk_keywords + source)
    ↓ embedder (BAAI/bge-small-en-v1.5)
    ↓ stored in ChromaDB
app/ai_services/ai_coach/chroma_db/

── On first API request ──
FastAPI starts → first /v1/plans/... request
    → VectorDBService loads ChromaDB from disk (~1s)
    → stays in memory for all subsequent requests
    → query expansion (base + retrieval-oriented variants)
    → hybrid rerank (semantic score + lexical overlap)
    → domain/topic filtering with fallback broadening
    → structured context blocks injected into Groq LLM prompt
    → LLM returns evidence-grounded plan
```

### Build the Vector Database

**Recommended (Docker):**
```bash
docker compose exec -T web python scripts/setup_vector_db.py
# Choose option 2 (HIGH priority, 17 sources, ~5 min)
```

**Local:**
```bash
pip install beautifulsoup4 requests pypdf langchain langchain-community chromadb sentence-transformers
python scripts/setup_vector_db.py
```

**Manual:**
```bash
# Step 1: Scrape sources
python scripts/scrape_fitness_resources.py 999 HIGH

# Step 2: Build vector store
python -c "from app.ai_services.ai_coach.vector_db_service import initialize_vector_db; initialize_vector_db(force_recreate=True)"
```

### Retrieval Pipeline (Current)

1. Infer `domain/topic` from query and apply metadata filters.
2. Generate query variants for better recall.
3. Retrieve semantic candidates from Chroma.
4. Re-rank with a combined score: semantic relevance + lexical overlap.
5. Format context as `[SOURCE | URL] + summary + keywords + content`.
6. Fallback broadening if filters are too narrow.

### Rebuild When
- ✅ First-time setup
- ✅ Added/changed URLs in `resources.csv`
- ✅ Changed chunking parameters

### Skip Rebuild When
- ❌ Server / container restart
- ❌ Code changes to AI service
- ❌ Every API call

### Data Sources (resources.csv)

| Category | Count | Examples |
|---|---|---|
| Exercise Programming | 7 | ACSM, NSCA, ExRx.net |
| Nutrition Guidelines | 4 | WHO, USDA FoodData Central |
| Sports Nutrition | 4 | ISSN Position Stands |
| Exercise Database | 4 | ExRx.net (2,100+ exercises) |
| Periodization | 3 | NASM, Linear/Block/Undulating |
| TDEE Calculators | 3 | Calculator.net, TDEE Calculator |
| Fitness Books (PDFs) | 2 | Army ROTC, Fitness for Dummies |

### Technical Details

| Parameter | Value |
|---|---|
| Embedding model | `BAAI/bge-small-en-v1.5` |
| Chunk size | ~2200 characters (~512-token equivalent) |
| Chunk overlap | 200 characters |
| Retrieval | Hybrid rerank (semantic + lexical overlap) |
| Default k | 3–5 documents |
| Query time | < 100ms |
| DB disk size | ~100–150MB (HIGH priority) |

---

## Scripts (Linux & Windows)

Use these commands to run project scripts locally or inside Docker.

### Local Environment

**Linux / macOS (Bash):**
```bash
source venv/bin/activate
```

**Windows (PowerShell):**
```powershell
venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```bat
venv\Scripts\activate.bat
```

### Food Import (`scripts/import_food.py`)

**Linux / macOS / Windows (local Python):**
```bash
# dry-run preview
python scripts/import_food.py

# import into DB
python scripts/import_food.py --import

# clear table then import
python scripts/import_food.py --import --clear
```

**Docker:**
```bash
docker compose exec -T web python scripts/import_food.py --import --clear
```

### Workout Import (`scripts/import_workouts.py`)

**Linux / macOS / Windows (local Python):**
```bash
# dry-run preview
python scripts/import_workouts.py

# import into DB
python scripts/import_workouts.py --import

# clear table then import
python scripts/import_workouts.py --import --clear
```

**Docker:**
```bash
docker compose exec -T web python scripts/import_workouts.py --import
```

### Scrape Fitness Sources (`scripts/scrape_fitness_resources.py`)

**Linux / macOS / Windows (local Python):**
```bash
# scrape top 3 HIGH-priority resources (quick test)
python scripts/scrape_fitness_resources.py 3 HIGH

# scrape all HIGH-priority resources
python scripts/scrape_fitness_resources.py 999 HIGH

# scrape all priorities
python scripts/scrape_fitness_resources.py 999 ALL
```

**Docker:**
```bash
docker compose exec -T web python scripts/scrape_fitness_resources.py 999 HIGH
```

### Build / Rebuild Vector DB (`scripts/setup_vector_db.py`)

**Linux / macOS / Windows (local Python):**
```bash
python scripts/setup_vector_db.py
```

**Docker:**
```bash
docker compose exec -T web python scripts/setup_vector_db.py
```

### One-Liner Vector DB Rebuild (Non-interactive)

**Linux / macOS / Windows (local Python):**
```bash
python -c "from app.ai_services.ai_coach.vector_db_service import initialize_vector_db; print(initialize_vector_db(force_recreate=True, source_type='scraped'))"
```

**Docker:**
```bash
docker compose exec -T web python -c "from app.ai_services.ai_coach.vector_db_service import initialize_vector_db; print(initialize_vector_db(force_recreate=True, source_type='scraped'))"
```

---

## AI Coach Evaluation (LLM-as-Judge)

The evaluation pipeline measures how accurately the AI Coach respects user constraints (injuries, allergies, equipment, dietary preferences) across a large batch of synthetic test cases.

### Why LLM-as-Judge?

Keyword matching misses **indirect** violations:

| Constraint | Plan output | Keyword result | Judge result |
|---|---|---|---|
| Tomato allergy | "Marinara Pasta" | ✅ Pass (no word "tomato") | ❌ Fail (tomato sauce) |
| Egg allergy | "Hollandaise Sauce" | ✅ Pass | ❌ Fail (egg-based) |
| Knee injury | "Depth Jumps" | ✅ Pass | ❌ Fail (high impact) |
| Vegan | "Greek Yogurt Parfait" | ✅ Pass | ❌ Fail (dairy) |

A second LLM call semantically audits each generated plan using world knowledge of ingredient composition and exercise biomechanics, catching violations that any keyword approach would miss.

---

### Package Structure

```
app/ai_services/evaluation/
├── __init__.py       # Package docstring
├── models.py         # CheckResult + EvalReport dataclasses
├── test_cases.py     # Synthetic profile generators
├── judge.py          # LLM-as-judge prompts + JSON parsing
├── evaluators.py     # Per-plan evaluation (rule-based + LLM judge)
├── reporting.py      # Aggregation, tables, accuracy banner
└── runner.py         # Main run_evaluation() loop

scripts/
└── evaluate_rag_pipeline.py   # Thin CLI wrapper (argparse → run_evaluation)
```

---

### Constraint Checks

**Workout plans** — 2 LLM calls per test case (1 generate + 1 judge)

| Check | Type | Weight | Applicable when |
|---|---|---|---|
| `days_count_match` | Rule-based | 10 | Always |
| `injury_safety` | LLM judge | 30 | User has stated injuries |
| `medical_condition_safety` | LLM judge | 30 | User has medical conditions |
| `equipment_compliance` | LLM judge | 25 | Always |
| `goal_alignment` | LLM judge | 15 | Always |

**Nutrition plans** — 2 LLM calls per test case

| Check | Type | Weight | Applicable when |
|---|---|---|---|
| `meals_count_match` | Rule-based | 10 | Always |
| `calorie_accuracy` (±15%) | Rule-based | 15 | Always |
| `allergen_safety` | LLM judge | 35 | User has food allergies |
| `dietary_preference_respected` | LLM judge | 25 | User has a diet preference |
| `exclusion_compliance` | LLM judge | 20 | User excluded ingredients |
| `goal_alignment` | LLM judge | 15 | Always |

> **Applicable-only scoring:** Checks marked inapplicable (e.g. `allergen_safety` when the user has no allergies) are excluded from the weighted average entirely — they do not inflate or deflate the score.

---

### Scoring & Grades

```
Overall score = weighted average of applicable checks (0–100%)
```

| Grade | Score |
|---|---|
| EXCELLENT | ≥ 90% |
| GOOD | ≥ 80% |
| FAIR | ≥ 70% |
| NEEDS IMPROVEMENT | < 70% |

Pass threshold per plan: **70%**

---

### Running the Evaluation

```bash
# Run 100 test cases (50 workout + 50 nutrition) — default
python3 scripts/evaluate_rag_pipeline.py

# Run 20 workout-only cases
python3 scripts/evaluate_rag_pipeline.py --samples 20 --plan-type workout

# Run 50 nutrition-only cases
python3 scripts/evaluate_rag_pipeline.py --samples 50 --plan-type nutrition

# Custom output file and rate-limit delay
python3 scripts/evaluate_rag_pipeline.py --output results/run1.json --delay 2.0
```

| Option | Default | Description |
|---|---|---|
| `--samples` | 100 | Total test cases |
| `--plan-type` | `both` | `workout` \| `nutrition` \| `both` |
| `--output` | `eval_results.json` | JSON results file |
| `--delay` | `1.5` | Seconds between API calls (rate limiting) |

> **Cost note:** Each test case makes **2 LLM calls** — one to generate the plan, one for the judge. 100 cases = 200 Groq API calls.

---

### Output

**Console — per-case progress:**
```
  [  1/50] goal=Weight Loss            equip=No Equipment         cond=—        … ✅ PASS  (92.3%)
  [  2/50] goal=Muscle Building        equip=Full Gym             cond=Knee Pain … ❌ FAIL  (58.0%)
```

**Console — accuracy banner (end of run):**
```
#######################################################
###                                                 ###
###   OVERALL MODEL ACCURACY                        ###
###   Score     :  85.4%                            ###
###   Pass Rate :  78 / 100  (78.0%)                ###
###   Grade     :  GOOD                             ###
###   Plans     :  100  evaluated                   ###
###                                                 ###
#######################################################
```

**JSON file** (`eval_results.json`) — machine-readable results with per-check breakdowns and full per-plan reports, suitable for trend analysis across runs.

---

### Test Case Generation

Profiles are generated deterministically from domain pools:

- **Goals:** Weight Loss, Muscle Building, Endurance, Flexibility, General Fitness
- **Medical conditions:** Hypertension, Diabetes Type 2, Knee Pain, Back Pain, Cardiac Condition, Asthma, …
- **Injuries:** Knee Injury, Shoulder Injury, Lower Back Pain, Ankle Sprain, …
- **Allergies:** Gluten, Dairy, Nuts, Eggs, Soy, Shellfish, **Tomatoes**, …
- **Dietary preferences:** Vegan, Vegetarian, Keto, Paleo, Halal, …

Workout cases: 25% no-equipment, 25% cardiac/joint conditions, 50% free.  
Nutrition cases: 33% forced allergies, 33% vegan/vegetarian, 33% free.

---

## Development Guidelines

### Adding a New Module

```bash
# Create structure
mkdir -p app/new_module/{models,repositories,services,routes,schemas}
touch app/new_module/__init__.py
touch app/new_module/{models,repositories,services,routes,schemas}/__init__.py
```

Register the router in `main.py`:
```python
from app.new_module.routes import new_router

v1_router.include_router(new_router, tags=["New Module"])
```

### Naming Conventions

| Layer | Pattern | Example |
|---|---|---|
| Model file | `singular.py` | `user.py`, `plan.py` |
| Repository | `entity_repository.py` | `user_repository.py` |
| Service | `entity_service.py` | `auth_service.py` |
| Routes | `entity_routes.py` | `workout_routes.py` |
| Router var | `entityRouter` or `entity_router` | `authRouter` |

### Import Patterns

```python
# ✅ Import from global core
from app.core.security import hash_password
from app.db.database import get_db

# ✅ Re-export in module core for convenience
# auth_module/core/__init__.py
from app.auth_module.core.security import generate_otp
from app.auth_module.core.dependencies import get_current_user

# ❌ Never duplicate code across modules
```

### Route Style (thin routes)

```python
# ✅ Correct — routes delegate everything to services
@router.post("/signup", response_model=UserResponse)
def signup(
    user_data: UserCreate,
    auth_service: AuthService = Depends(get_auth_service)
):
    return auth_service.create_user(user_data)

# ❌ Wrong — business logic in routes
@router.post("/signup")
def signup(user_data: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(...)
    # ... 50 more lines
```

---

## Troubleshooting

### App won't start — `JWT_SECRET_KEY` error
`JWT_SECRET_KEY` is required and has no default. Set it in `.env` or Railway variables:
```bash
JWT_SECRET_KEY=$(openssl rand -hex 32)
```

### Database connection error
```bash
# Check containers are healthy
docker-compose ps
# Restart if needed
docker-compose restart db
```

### Redis connection failed
```bash
docker exec -it FitMind_Redis redis-cli ping
# Expected: PONG
```

### Email verification not working
- Ensure `SENDER_EMAIL` and `SENDER_PASSWORD` are set
- Use a Gmail **App Password** (not your regular password) — [Get one here](https://myaccount.google.com/apppasswords)
- Verify `APP_URL` points to the correct base URL (e.g. `https://your-app.up.railway.app`)

### Vector DB not found
```
FileNotFoundError: Vector database not found at app/ai_services/ai_coach/chroma_db/
```
Run the setup script:
```bash
docker-compose exec web python scripts/setup_vector_db.py
```

### ChromaDB telemetry warning
```
Failed to send telemetry event ClientStartEvent: ...
```
Harmless — ChromaDB still works fine. Can be silenced by setting `ANONYMIZED_TELEMETRY=False` in your env.

### `.env` changes not taking effect in Docker
```bash
docker-compose down
docker-compose up --build
```

### Port already in use
Change the host port mapping in `docker-compose.yml`:
```yaml
ports:
  - "8001:8000"   # Use 8001 on host instead
```
