# FitMind System Architecture

Paste the diagram below into [eraser.io](https://app.eraser.io/) using **Diagram as Code** mode (select "Architecture" type).

```eraser
cloud-architecture-diagram

// ─── Client Layer ───
Mobile App [icon: smartphone, label: "Flutter Mobile App"] {
  Android Client [icon: android]
  iOS Client [icon: apple]
}

// ─── API Gateway ───
FastAPI [icon: server, label: "FastAPI Backend", color: green] {
  Auth Module [icon: lock, label: "Auth Module"]
  Profile Module [icon: user, label: "Profile Module"]
  Planning Module [icon: clipboard, label: "Planning Module"]
  Tracking Module [icon: activity, label: "Tracking Module"]
  Notification Module [icon: bell, label: "Notification Module"]
  Recommendation Module [icon: star, label: "Recommendation Module"]
}

// ─── Background Workers ───
Celery Workers [icon: settings, label: "Celery Workers", color: orange] {
  Beat Scheduler [icon: clock, label: "Beat Scheduler"]
  Task Worker [icon: cpu, label: "Task Worker"]
}

// ─── AI Services ───
AI Services [icon: cpu, label: "AI Services", color: purple] {
  AI Coach [icon: brain, label: "AI Coach Engine"]
  Meal Scanner [icon: camera, label: "Meal Scanner"]
  Voice Transcriber [icon: mic, label: "Voice Transcriber"]
}

// ─── External AI ───
LLM Gateway [icon: cloud, label: "LLM Gateway (OpenRouter)"]
Whisper API [icon: cloud, label: "Whisper API (Groq)"]

// ─── Data Layer ───
PostgreSQL [icon: database, label: "PostgreSQL + pgvector", color: blue]
Redis [icon: database, label: "Redis Cache", color: red]
ChromaDB [icon: database, label: "ChromaDB (RAG)", color: yellow]

// ─── External Services ───
FCM [icon: cloud, label: "Firebase Cloud Messaging"]
SMTP [icon: mail, label: "SMTP Email"]

// ─── Connections ───

// Client to API
Mobile App --> FastAPI: REST API (HTTPS)

// API to Data
Auth Module --> PostgreSQL: Users
Auth Module --> Redis: Tokens & OTP
Profile Module --> PostgreSQL: Profiles
Planning Module --> PostgreSQL: Plans
Planning Module --> AI Coach: Plan Generation
Tracking Module --> PostgreSQL: Logs
Tracking Module --> Meal Scanner: Image Analysis
Tracking Module --> Voice Transcriber: Audio Processing
Notification Module --> PostgreSQL: Preferences
Notification Module --> FCM: Push Notifications
Recommendation Module --> PostgreSQL: Coaching Messages

// AI to External
AI Coach --> LLM Gateway: Plan Generation & Validation
AI Coach --> ChromaDB: RAG Context Retrieval
AI Coach --> PostgreSQL: pgvector Food/Exercise Matching
Meal Scanner --> LLM Gateway: Vision Model (Qwen2.5-VL)
Meal Scanner --> PostgreSQL: pgvector Food Matching
Voice Transcriber --> Whisper API: Speech-to-Text
Voice Transcriber --> LLM Gateway: Text Parsing
Voice Transcriber --> PostgreSQL: pgvector Food Matching

// Background Workers
Celery Workers --> Redis: Task Queue
Beat Scheduler --> Task Worker: Scheduled Tasks
Task Worker --> Notification Module: Reminders
Task Worker --> Recommendation Module: Daily/Weekly Coaching

// Auth External
Auth Module --> SMTP: Verification & Reset Emails
```

## If eraser.io doesn't accept the format above, use this simplified text description:

### Architecture Layers (top to bottom):

**1. Client Layer**
- Flutter Mobile App (Android + iOS)

**2. API Layer — FastAPI Backend**
- Auth Module (signup, login, email verification, password reset)
- Profile Module (CRUD user profiles)
- Planning Module (AI-generated workout & nutrition plans)
- Tracking Module (meals, workouts, weight, sleep, hydration logs + AI scanning/voice)
- Notification Module (device tokens, preferences, push via FCM)
- Recommendation Module (coaching messages, FitMind Score, suggestions)

**3. Background Processing — Celery + Redis**
- Beat Scheduler: 6 periodic tasks (hydration/meal/workout/sleep reminders, daily/weekly coaching)
- Task Worker: executes reminder checks and coaching generation

**4. AI Services Layer**
- AI Coach Engine: prompt building → LLM Gateway → plan validation → plan judging
- Meal Scanner: image → Vision LLM → pgvector food matching
- Voice Transcriber: audio → Whisper → LLM parsing → pgvector matching

**5. Data Layer**
- PostgreSQL + pgvector: all relational data + 384-dim vector embeddings for food/exercise similarity search
- Redis: session tokens, OTPs, Celery task queue
- ChromaDB: RAG knowledge base (scraped fitness resources, ~1900 chunks)

**6. External Services**
- LLM Gateway: unified AI model access (plan generation, validation, meal scanning, voice parsing)
- Whisper API: speech-to-text transcription
- Firebase Cloud Messaging: push notifications to mobile devices
- SMTP: email delivery (verification, password reset)

### Key Data Flows:
1. **Plan Generation**: User → API → ThreadPoolExecutor (parallel) → AI Coach → ChromaDB (RAG) + LLM Gateway → Plan Validator → Plan Judge → pgvector (match foods/exercises) → PostgreSQL
2. **Meal Voice Log**: User → API → Whisper (transcribe) → LLM (parse) → pgvector (match foods) → Response
3. **Meal Scan**: User → API → Vision LLM (identify) → pgvector (match foods) → Response
4. **Automated Reminders**: Celery Beat → Worker → Check preferences → Check plans/logs → FCM → User device
5. **AI Coaching**: Celery Beat → Worker → Gather 24h data → LLM (generate tip) → Save message → FCM → User device
