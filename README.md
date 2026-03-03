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
12. [Development Guidelines](#development-guidelines)
13. [Troubleshooting](#troubleshooting)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI |
| Database | PostgreSQL 16 (SQLAlchemy ORM) |
| Cache / OTP Store | Redis 7 |
| Authentication | JWT + bcrypt |
| AI / LLM | Groq API (Llama, Mixtral, Whisper) |
| Vector DB | ChromaDB + HuggingFace `all-MiniLM-L6-v2` |
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
│   └── setup_vector_db.py          # Builds ChromaDB vector store
├── data/
│   └── scraped_resources/
│       └── scraped_documents.json
└── app/
    ├── core/                        # Global config, security, Redis client
    ├── db/                          # SQLAlchemy engine & session
    ├── shared/                      # Base repository, shared email service
    ├── ai_services/                 # AI integrations (Groq wrappers)
    │   ├── ai_coach/                # RAG-based plan generation
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

POST /v1/auth/verify-reset-otp
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
    ↓ chunker (1000 chars, 200 overlap)
    ↓ embedder (all-MiniLM-L6-v2 → 384-dim vectors)
    ↓ stored in ChromaDB
app/ai_services/ai_coach/chroma_db/

── On first API request ──
FastAPI starts → first /v1/plans/... request
    → VectorDBService loads ChromaDB from disk (~1s)
    → stays in memory for all subsequent requests
    → similarity_search(query, k=5) → top chunks
    → chunks injected into Groq LLM prompt
    → LLM returns evidence-grounded plan
```

### Build the Vector Database

**Recommended (Docker):**
```bash
docker-compose exec web python scripts/setup_vector_db.py
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
| Embedding model | `all-MiniLM-L6-v2` (384-dim, ~90MB) |
| Chunk size | 1000 characters |
| Chunk overlap | 200 characters |
| Similarity | Cosine similarity |
| Default k | 3–5 documents |
| Query time | < 100ms |
| DB disk size | ~100–150MB (HIGH priority) |

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

## Feature Engineering & Feature Generation (Tracking Module)

### Concept

**Feature Engineering** = designing which signals matter (plateau, adherence rate, trend direction, streak).  
**Feature Generation** = automatically computing those signals over time as users log data.

Raw logs alone carry no insight. Derived features make the data actionable and allow Groq to give personalized, accurate advice instead of generic responses.

```
Raw logs (weights, workouts, meals)
    ↓  feature_service.py (pure Python math)
Computed features (rates, trends, streaks, scores)
    ↓  injected into Groq prompt
Natural language insights + actionable recommendations
    ↓  returned to user via /v1/tracking/insights
```

---

### Planned Module Structure

```
tracking_module/
├── models/
│   ├── weight_log.py             → WeightLog DB model
│   ├── workout_log.py            → WorkoutLog DB model
│   └── meal_log.py               → MealLog DB model
├── repositories/
│   └── log_repository.py         → DB queries for raw + aggregated data
├── services/
│   ├── log_service.py            → save raw user logs
│   └── feature_service.py        → compute features from logs  ← key file
├── routes/
│   ├── log_routes.py             → POST /v1/tracking/logs/...
│   └── insights_routes.py        → GET /v1/tracking/insights
└── schemas/
    ├── log.py                    → request/response for logs
    └── insights.py               → InsightsDTO response schema
```

---

### Features to Compute (`feature_service.py`)

#### Weight Features
| Feature | How | Alert Condition |
|---|---|---|
| `weekly_weight_change_kg` | avg(last 7 days) − avg(prev 7 days) | Negative if losing, positive if gaining |
| `weight_trend_slope` | linear regression over last N entries | Tells if direction is correct |
| `plateau_detected` | `abs(weekly_change) < 0.2` for 2+ weeks | Warn user, suggest adjusting calories |
| `goal_pace_adherence` | `actual_rate / target_rate` | < 0.5 → too slow, > 1.5 → too fast |
| `consistency_score` | logs_done / days_since_start | < 0.6 → prompt user to log more |

#### Workout Features
| Feature | How | Alert Condition |
|---|---|---|
| `workout_completion_rate` | completed / planned sessions | < 0.6 → missed too many sessions |
| `missed_days_streak` | consecutive missed workout days | ≥ 3 → send a motivation alert |
| `volume_progression` | this week's total volume / last week's | Ensure progressive overload |

#### Nutrition Features
| Feature | How | Alert Condition |
|---|---|---|
| `avg_daily_calories` | rolling 7-day average | Compare to plan target |
| `macro_adherence_score` | actual macros vs. target macros | Flag large deviations |
| `meal_log_consistency` | meals_logged / target_meals | < 0.5 → encourage logging |

---

### Implementation Pattern

**Step 1 — Compute features in pure Python (no AI needed):**

```python
# tracking_module/services/feature_service.py
from statistics import mean

def compute_progress_features(user_id: int, db) -> dict:
    weight_logs = log_repo.get_last_30_days_weights(user_id, db)
    workout_logs = log_repo.get_current_week_workouts(user_id, db)
    calorie_logs = log_repo.get_last_7_days_calories(user_id, db)

    weekly_avg_now  = mean([l.weight for l in weight_logs[-7:]])  if len(weight_logs) >= 7  else None
    weekly_avg_prev = mean([l.weight for l in weight_logs[-14:-7]]) if len(weight_logs) >= 14 else None

    return {
        "weekly_weight_change_kg":  round(weekly_avg_now - weekly_avg_prev, 2) if weekly_avg_now and weekly_avg_prev else None,
        "plateau_detected":         abs(weekly_avg_now - weekly_avg_prev) < 0.2 if weekly_avg_now and weekly_avg_prev else False,
        "workout_completion_rate":  workout_logs.completed / workout_logs.planned if workout_logs.planned else 0,
        "missed_days_streak":       workout_logs.consecutive_missed,
        "avg_daily_calories":       round(mean(calorie_logs), 0) if calorie_logs else None,
        "weeks_tracked":            len(weight_logs) // 7,
    }
```

**Step 2 — Inject features into a Groq prompt:**

```python
# tracking_module/services/insights_service.py
from groq import Groq
import os

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def generate_insights(features: dict, user_profile: dict) -> str:
    prompt = f"""
You are a professional fitness coach analyzing a user's weekly progress.

USER PROFILE:
- Goal: {user_profile['goal']}
- Target weekly weight change: {user_profile['weekly_target_kg']} kg/week

THIS WEEK'S COMPUTED METRICS:
- Weight change this week:     {features['weekly_weight_change_kg']} kg
- Plateau detected:            {features['plateau_detected']}
- Workout completion rate:     {features['workout_completion_rate'] * 100:.0f}%
- Consecutive missed days:     {features['missed_days_streak']}
- Avg daily calories:          {features['avg_daily_calories']} kcal
- Weeks tracked so far:        {features['weeks_tracked']}

Based on these metrics:
1. Is the user on track with their goal?
2. What specific problems do you notice?
3. Give 2-3 actionable, personalized recommendations using the actual numbers.
4. Adjust tone — encouraging if doing well, motivating if struggling.

Be concise and specific. Always reference the actual numbers in your response.
"""
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=600,
    )
    return response.choices[0].message.content
```

**Step 3 — Wire into the insights route:**

```python
# tracking_module/routes/insights_routes.py
@router.get("/insights", response_model=InsightsResponse)
def get_insights(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile = profile_repo.get_by_user_id(current_user.id, db)
    features = feature_service.compute_progress_features(current_user.id, db)
    advice   = insights_service.generate_insights(features, profile)
    return InsightsResponse(features=features, ai_advice=advice)
```

---

### Why This Works With Groq

| What your Python computes | What Groq adds |
|---|---|
| Exact numbers (0.4 kg loss) | Natural language interpretation |
| Rates, streaks, averages | Context-aware, personalized tone |
| Boolean flags (plateau=True) | Nuanced advice beyond simple if/else rules |
| Structured feature dict | Conversational, motivating feedback |

Without features → Groq gives generic advice.  
With features → Groq responds to the user's **actual numbers**, making it feel genuinely intelligent.

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
