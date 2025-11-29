# FitMind Backend Architecture

## 📁 Project Structure Overview

```
app/
├── core/                    # Global shared configurations
│   ├── config.py           # Application-wide settings
│   ├── dependencies.py     # Common dependency injections
│   ├── redis_client.py     # Redis singleton
│   └── security.py         # Password hashing, JWT tokens
│
├── shared/                  # Shared utilities across modules
│   ├── repositories/       # Base repository pattern
│   ├── services/           # Shared services (email)
│   ├── schemas/            # Common Pydantic schemas
│   └── utils/              # Helper functions
│
├── ai_services/            # External AI integrations
│   ├── ai_coach/           # Groq API for plan generation
│   ├── meal_scanner/       # Food recognition
│   └── voice_transcriber/  # Audio transcription
│
├── auth_module/            # User authentication
├── profile_module/         # User health profiles
├── planning_module/        # Workout & nutrition plans
├── tracking_module/        # Progress tracking
├── chatbot_module/         # AI conversational coach
└── notification_module/    # User notifications
```

## 🏗️ Architecture Patterns

### 1. Layered Architecture (Per Module)

Each module follows clean separation:

```
module/
├── models/         # Database entities (SQLAlchemy)
├── repositories/   # Data access layer
├── services/       # Business logic layer
├── routes/         # API endpoints (FastAPI)
└── schemas/        # Request/response validation (Pydantic)
```

**Data Flow:**
```
Request → Route → Service → Repository → Database
                     ↓
                AI Service (optional)
```

### 2. Re-Export Pattern (auth_module/core)

**Problem:** Avoid code duplication while providing module-specific extensions.

**Solution:** Module-specific core folders re-export from `app/core`:

```python
# auth_module/core/security.py
from app.core.security import hash_password, verify_password  # Re-export
# + Module-specific extensions:
def generate_otp(): ...
def generate_verification_token(): ...
```

**Benefits:**
- ✅ Single source of truth (`app/core`)
- ✅ Module-specific additions (OTP, verification tokens)
- ✅ Clean imports within module
- ✅ No code duplication

### 3. Dependency Injection

Using FastAPI's `Depends()` for clean dependency management:

```python
# auth_module/core/dependencies.py
def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
    verification_service: VerificationService = Depends(get_verification_service)
) -> AuthService:
    return AuthService(user_repo, verification_service)

# Usage in routes
@router.post("/register")
def register(
    auth_service: AuthService = Depends(get_auth_service)
):
    return auth_service.create_user(...)
```

## 🔐 Authentication & Security

### Shared Security (`app/core/security.py`)
- Password hashing (bcrypt)
- JWT token generation/verification
- Generic hashing utilities

### Auth-Specific Security (`auth_module/core/security.py`)
- OTP generation (5-digit codes)
- Email verification tokens
- OTP hashing/verification

### Configuration
- **Global:** `app/core/config.py` (JWT, Redis, SMTP, Database)
- **Auth-Specific:** `auth_module/core/config.py` (OTP length, expiration)

## 🤖 AI Services Architecture

### Hybrid Approach (Recommended)

```
Planning Module → AI Services (Wrappers) → External APIs
                                            ├── Groq API
                                            ├── OpenAI API
                                            └── Hugging Face API
```

**Advantages:**
- Leverage managed AI services
- No heavy model hosting
- Simple deployment
- Cost-effective for MVP
- Easy to scale

### AI Service Structure

```
ai_services/
├── ai_coach/
│   ├── client.py       # Groq API wrapper
│   ├── prompts.py      # Prompt templates
│   └── vector_store.py # RAG for fitness knowledge
├── meal_scanner/
│   └── client.py       # Food recognition API
└── voice_transcriber/
    └── client.py       # Whisper API wrapper
```

## 📊 Database Design

### Entity Relationships

```
users (1) ──── (0..1) profiles
users (1) ──── (many) workout_plans
users (1) ──── (many) nutrition_plans
users (1) ──── (many) workout_logs
users (1) ──── (many) meal_logs

profiles (1) ──── (many) workout_plans
profiles (1) ──── (many) nutrition_plans

workout_plans (1) ──── (many) workout_days
workout_days (1) ──── (many) exercises

nutrition_plans (1) ──── (many) meals
```

### Key Design Decisions

1. **Profile → Plan Relationship:**
   - Plans reference profile_id (for AI context)
   - Preferences stored as JSON in plan (no separate request table)

2. **Plan Preferences:**
   - Stored in `generated_from_preferences` JSON column
   - Enables regeneration and history tracking
   - No separate plan_requests table needed

## 🔄 Request Flow Example

### Generate Workout Plan

```
1. User fills plan request form
   └── POST /planning/workout-plans/generate
       {
         "plan_type": "WORKOUT_ONLY",
         "duration_weeks": 8,
         "workout_preferences": {
           "workout_days_per_week": 4,
           "workout_location": "GYM",
           "equipment_availability": "FULL_GYM",
           ...
         }
       }

2. WorkoutPlanService receives request
   ├── Validates user has profile
   ├── Fetches profile (health data)
   └── Calls AICoachClient

3. AICoachClient (future)
   ├── Builds prompt from profile + preferences
   ├── Calls Groq API
   └── Parses structured response

4. WorkoutPlanService saves plan
   ├── Creates WorkoutPlan entity
   ├── Creates WorkoutDay entities
   ├── Creates Exercise entities
   └── Stores preferences as JSON

5. Returns complete plan to user
```

## 🎯 Module Status

| Module                | Status        | Description                            |
| --------------------- | ------------- | -------------------------------------- |
| `auth_module`         | ✅ Complete    | User registration, login, verification |
| `profile_module`      | ✅ Complete    | Health profiles, BMR/TDEE calculations |
| `planning_module`     | 🟡 In Progress | Models, repos, routes done; AI pending |
| `tracking_module`     | ⏳ Planned     | Workout/meal/weight logging            |
| `chatbot_module`      | ⏳ Planned     | AI conversational coach                |
| `notification_module` | ⏳ Planned     | Push notifications, reminders          |
| `ai_services`         | ⏳ Planned     | External AI API integrations           |

## 🚀 Development Guidelines

### Adding a New Module

1. Create module structure:
```
new_module/
├── __init__.py
├── models/
├── repositories/
├── services/
├── routes/
└── schemas/
```

2. Follow naming conventions:
- Models: `singular_noun.py` (e.g., `user.py`, `workout_plan.py`)
- Repositories: `entity_repository.py`
- Services: `entity_service.py`
- Routes: `entity_routes.py`

3. Use dependency injection
4. Add type hints everywhere
5. Write docstrings for public methods

### Import Patterns

```python
# ✅ Good: Import from shared core
from app.core.security import hash_password
from app.db.database import get_db

# ✅ Good: Re-export in module core for convenience
# auth_module/core/security.py
from app.core.security import hash_password
__all__ = ["hash_password", "generate_otp"]

# ❌ Bad: Duplicate code across modules
```

### Testing Strategy

```
tests/
├── unit/           # Fast, isolated tests
│   ├── services/
│   ├── repositories/
│   └── utils/
├── integration/    # Database + API tests
│   └── routes/
└── e2e/           # Full user journey tests
```

## 📝 Key Architectural Decisions

### 1. Why Monolithic (for now)?
- ✅ Faster development
- ✅ Simpler deployment
- ✅ Shared database transactions
- ✅ Good for MVP
- 🔄 Can migrate to microservices later

### 2. Why External AI APIs?
- ✅ No GPU infrastructure needed
- ✅ Cost-effective for startup
- ✅ Always up-to-date models
- ✅ Pay-as-you-go pricing
- 🔄 Can self-host if costs scale

### 3. Why Synchronous (not async)?
- ✅ Simpler code
- ✅ Easier debugging
- ✅ SQLAlchemy ORM is sync
- ✅ Sufficient for current scale
- 🔄 Can migrate to async SQLAlchemy later

### 4. Why Module-Specific Core Folders?
- ✅ Clean re-exports from shared core
- ✅ Module-specific extensions
- ✅ Backward compatibility
- ✅ Clear separation of concerns

## 🔧 Technology Stack

- **Framework:** FastAPI
- **Database:** PostgreSQL (SQLAlchemy ORM)
- **Cache:** Redis
- **Authentication:** JWT + bcrypt
- **AI:** Groq API, OpenAI API
- **Validation:** Pydantic
- **Documentation:** Auto-generated (FastAPI + Swagger)

## 📚 Further Reading

- [FastAPI Dependency Injection](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [SQLAlchemy Relationships](https://docs.sqlalchemy.org/en/20/orm/relationships.html)
- [Pydantic Models](https://docs.pydantic.dev/latest/)
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)

---

**Last Updated:** November 29, 2025  
**Branch:** Feature/Planning
