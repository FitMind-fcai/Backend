# FitMind Backend — Command Reference

All commands run **inside Docker**. No virtualenv, no local Python needed.

---

## Table of Contents

1. [First-Time Setup](#1-first-time-setup)
2. [Start / Stop Services](#2-start--stop-services)
3. [Database Migrations (Alembic)](#3-database-migrations-alembic)
4. [Seeding & Data Import](#4-seeding--data-import)
5. [Vector DB (ChromaDB)](#5-vector-db-chromadb)
6. [Running the API Server](#6-running-the-api-server)
7. [Celery (Task Queue & Scheduler)](#7-celery-task-queue--scheduler)
8. [Tests (unit · integration · evaluation)](#8-tests-unit--integration--evaluation)
9. [Code Quality](#9-code-quality)
10. [Logs & Debugging](#10-logs--debugging)
11. [Cleanup](#11-cleanup)

---

## 1. First-Time Setup

```bash
# 1. Clone the repo
git clone https://github.com/fitmind-fcai/backend.git
cd backend

# 2. Create your .env file from the example
cp .env.example .env
# Edit .env and fill in real values for:
#   AI_API_KEY, GROQ_API_KEY, SENDER_EMAIL, SENDER_PASSWORD,
#   JWT_SECRET_KEY, FIREBASE_CREDENTIALS_PATH (optional)

# 3. Build the Docker image
docker compose build
```

---

## 2. Start / Stop Services

The stack has 5 services: **db** (PostgreSQL + pgvector), **redis**, **web** (FastAPI), **celery_worker**, **celery_beat**.

```bash
# Start everything (runs migrations + seed on first boot automatically)
docker compose up

# Start in the background
docker compose up -d

# Start only the database and redis (useful for running tests)
docker compose up -d db redis

# Start only the API (without Celery)
docker compose up -d db redis web

# Stop all services (keeps volumes / data)
docker compose stop

# Stop and remove containers (keeps volumes / data)
docker compose down
```

---

## 3. Database Migrations (Alembic)

All migration commands run **inside the `web` container** so they use the correct `DATABASE_URL`.

```bash
# Apply all pending migrations (runs automatically on container start)
docker exec FitMind_APIs alembic upgrade head

# Roll back the last migration
docker exec FitMind_APIs alembic downgrade -1

# Roll back to a specific revision
docker exec FitMind_APIs alembic downgrade <revision_id>

# Generate a new migration after changing a model
docker exec FitMind_APIs alembic revision --autogenerate -m "describe the change"

# Show current migration revision
docker exec FitMind_APIs alembic current

# Show full migration history
docker exec FitMind_APIs alembic history --verbose

# Show pending migrations
docker exec FitMind_APIs alembic history --indicate-current
```

---

## 4. Seeding & Data Import

The entrypoint script (`entrypoint.sh`) handles seeding automatically on first boot. Use the commands below to trigger it manually.

```bash
# Full seed — imports foods (nutrition.csv) + exercises (megaGymDataset.csv)
# + generates pgvector embeddings. Runs automatically if the DB is empty.
docker exec FitMind_APIs python -m scripts.seed

# Fill only missing embeddings (fast, skips already-embedded rows)
docker exec FitMind_APIs python -m scripts.seed --embed-only

# Wipe all food/exercise data and re-seed from scratch
docker exec FitMind_APIs python -m scripts.seed --clear

# Import foods only
docker exec FitMind_APIs python -m scripts.import_food

# Import workouts only
docker exec FitMind_APIs python -m scripts.import_workouts

# Generate food pgvector embeddings only
docker exec FitMind_APIs python -m scripts.generate_food_embeddings

# Generate exercise pgvector embeddings only
docker exec FitMind_APIs python -m scripts.generate_exercise_embeddings

# Generate Arabic food nutrition data (requires AI_API_KEY)
docker exec FitMind_APIs python -m scripts.generate_arabic_food_nutrition
```

**Force re-seed via environment variable (restart required):**

```bash
# Set in .env or docker-compose.yml before starting:
RESEED_DB=true docker compose up web
```

---

## 5. Vector DB (ChromaDB)

```bash
# Build ChromaDB from existing scraped JSON (if chroma_db dir is missing)
docker exec FitMind_APIs python -m scripts.init_vector_db

# Re-scrape merged_resources.csv THEN rebuild ChromaDB
docker exec FitMind_APIs python -m scripts.init_vector_db --scrape --force-rebuild

# Force-rebuild from existing scraped data (no re-scrape)
docker exec FitMind_APIs python -m scripts.init_vector_db --force-rebuild

# Scrape fitness resources (saves to data/scraped_resources/)
docker exec FitMind_APIs python -m scripts.scrape_fitness_resources

# Set up / rebuild vector DB (legacy helper)
docker exec FitMind_APIs python -m scripts.setup_vector_db

# Evaluate RAG pipeline quality
docker exec FitMind_APIs python -m scripts.evaluate_rag_pipeline
```

**Force rebuild via environment variable:**

```bash
REBUILD_VECTOR_DB=true SCRAPE_RESOURCES=true docker compose up web
```

---

## 6. Running the API Server

```bash
# Normal start (via docker compose — recommended)
docker compose up web

# Start with hot-reload for development
docker exec -it FitMind_APIs uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# API is available at:
#   http://localhost:8000
#   http://localhost:8000/docs      (Swagger UI)
#   http://localhost:8000/redoc     (ReDoc)
#   http://localhost:8000/health    (health check)
```

---

## 7. Celery (Task Queue & Scheduler)

```bash
# Start Celery worker (runs via docker compose automatically)
docker compose up celery_worker

# Start Celery beat scheduler (runs via docker compose automatically)
docker compose up celery_beat

# Inspect active Celery tasks
docker exec FitMind_Celery_Worker celery -A app.celery_app.celery_app inspect active

# Inspect registered tasks
docker exec FitMind_Celery_Worker celery -A app.celery_app.celery_app inspect registered

# Purge all pending tasks from the queue
docker exec FitMind_Celery_Worker celery -A app.celery_app.celery_app purge -f

# Monitor tasks in real-time
docker exec -it FitMind_Celery_Worker celery -A app.celery_app.celery_app events
```

---

## 8. Tests (unit · integration · evaluation)

> Tests live on the **`testing` branch**. Switch to it before running any of the commands below.

```bash
git checkout testing
```

### Prerequisites

The full stack must be running (the web container has all test dependencies installed):

```bash
docker compose up -d db redis web
```

### Run All Tests

```bash
# All unit + integration tests (no real DB or external API calls needed — all mocked)
docker exec FitMind_APIs pytest

# With verbose output and coverage report
docker exec FitMind_APIs pytest -v --cov=app --cov-report=term-missing
```

### Run by Marker

```bash
# Unit tests only (pure Python, zero I/O)
docker exec FitMind_APIs pytest -m unit

# Integration tests only (FastAPI TestClient, all services mocked)
docker exec FitMind_APIs pytest -m integration
```

### Run a Specific Test File

```bash
docker exec FitMind_APIs pytest tests/unit/test_security.py
docker exec FitMind_APIs pytest tests/unit/test_auth_service.py
docker exec FitMind_APIs pytest tests/unit/test_profile_schemas.py
docker exec FitMind_APIs pytest tests/integration/test_auth.py
docker exec FitMind_APIs pytest tests/integration/test_profile.py
docker exec FitMind_APIs pytest tests/integration/test_tracking.py
docker exec FitMind_APIs pytest tests/integration/test_coaching.py
```

### Run a Specific Test Class or Function

```bash
# Single class
docker exec FitMind_APIs pytest tests/unit/test_security.py::TestPasswordHashing

# Single function
docker exec FitMind_APIs pytest tests/unit/test_security.py::TestPasswordHashing::test_correct_password_verifies
```

### AI Evaluation Scripts

Evaluation scripts call the **real `AICoachService`** (via `AI_API_KEY` / OpenRouter) to generate plans and coaching messages, then use a **Groq LLM** (`EVAL_GROQ_API_KEY`) as an independent safety judge. The two keys are kept separate so the coach and judge are completely independent.

| Script | `AI_API_KEY` | `EVAL_GROQ_API_KEY` |
|---|---|---|
| `run_evaluations.py` (all) | Required | Required |
| `eval_plan_safety.py` | Required | Required |
| `eval_coaching_relevance.py` | Required | Not needed |

```bash
# Run all evaluations (plan safety + coaching relevance) — saves combined_evaluation_report.json
docker exec \
  -e AI_API_KEY=sk-or-your-openrouter-key \
  -e EVAL_GROQ_API_KEY=gsk_your_groq_key \
  FitMind_APIs \
  python tests/evaluation/run_evaluations.py

# Plan safety only (3 profiles: Type 2 Diabetes, Knee ACL Injury, Exercise-Induced Asthma)
docker exec \
  -e AI_API_KEY=sk-or-your-openrouter-key \
  -e EVAL_GROQ_API_KEY=gsk_your_groq_key \
  FitMind_APIs \
  python tests/evaluation/eval_plan_safety.py

# Coaching relevance only (5 daily log scenarios — no Groq key needed)
docker exec \
  -e AI_API_KEY=sk-or-your-openrouter-key \
  FitMind_APIs \
  python tests/evaluation/eval_coaching_relevance.py

# Custom Groq judge model (default: llama-3.3-70b-versatile)
docker exec \
  -e AI_API_KEY=sk-or-your-openrouter-key \
  -e EVAL_GROQ_API_KEY=gsk_your_groq_key \
  -e EVAL_GROQ_MODEL=llama-3.1-70b-versatile \
  FitMind_APIs \
  python tests/evaluation/run_evaluations.py

# Custom output directory for results
docker exec \
  -e AI_API_KEY=sk-or-your-openrouter-key \
  -e EVAL_GROQ_API_KEY=gsk_your_groq_key \
  -e RESULTS_DIR=/app/eval_output \
  FitMind_APIs \
  python tests/evaluation/run_evaluations.py
```

Results are saved to `tests/evaluation/results/` inside the container.

### Run Tests Without the Full Stack

Unit and integration tests mock all services — they don't need a real database or Redis:

```bash
# Build the image first
docker build -t fitmind-backend .

# Run unit + integration tests, bypassing the entrypoint (no DB startup)
docker run --rm \
  --entrypoint "" \
  fitmind-backend \
  pytest -m "unit or integration" -v
```

---

## 9. Code Quality

```bash
# Format code with Black
docker exec FitMind_APIs black app/ main.py

# Check formatting without changing files
docker exec FitMind_APIs black --check app/ main.py

# Lint with Flake8
docker exec FitMind_APIs flake8 app/ main.py --max-line-length=120

# Type-check with mypy
docker exec FitMind_APIs mypy app/ main.py

# Lint with pylint
docker exec FitMind_APIs pylint app/ main.py
```

---

## 10. Logs & Debugging

```bash
# Follow logs for all services
docker compose logs -f

# Follow logs for a specific service
docker compose logs -f web
docker compose logs -f db
docker compose logs -f redis
docker compose logs -f celery_worker
docker compose logs -f celery_beat

# Last 100 lines of the API container
docker logs --tail 100 FitMind_APIs

# Open a shell inside the API container
docker exec -it FitMind_APIs bash

# Open a PostgreSQL prompt
docker exec -it FitMind_DB psql -U postgres -d fastapi_db

# Run a one-off Python command inside the container
docker exec FitMind_APIs python -c "from app.db.database import engine; print(engine.url)"

# Check container resource usage
docker stats
```

---

## 11. Cleanup

```bash
# Stop and remove containers only (volumes and data preserved)
docker compose down

# Remove containers AND all named volumes (wipes DB, ChromaDB, model cache)
docker compose down -v

# Remove only the database volume (forces fresh seed on next start)
docker volume rm backend_postgres_data

# Remove only the ChromaDB volume (forces rebuild on next start)
docker volume rm backend_chroma_data

# Remove only the model cache volume (re-downloads embedding model)
docker volume rm backend_models_cache

# Remove the built image (forces full rebuild on next `docker compose up`)
docker rmi backend-web

# Full reset — remove everything including the image
docker compose down -v
docker rmi backend-web
docker compose build --no-cache
```
