# Coaching Engine — Implementation

## Architecture

The coaching engine is a **thin scheduling layer** on top of existing feature engineering.
It reuses `RecommendationService.get_daily_suggestion()` and `get_progress_report()` —
no feature duplication.

Scheduling uses the **existing Celery + Redis** infrastructure from the notification module.
Push delivery uses the **existing Firebase push service**.

```
app/
├── recommendation_system/
│   ├── services/
│   │   ├── recommendation_service.py   ← existing feature engineering (untouched)
│   │   └── coaching_service.py         ← NEW: orchestrates checks + push
│   ├── models/
│   │   └── coaching_message.py         ← NEW: persists sent messages
│   ├── repositories/
│   │   └── coaching_message_repository.py  ← NEW
│   ├── routes/
│   │   ├── recommendations.py          ← existing (untouched)
│   │   └── coaching.py                 ← NEW: status, messages, read/dismiss
│   └── schemas/
│       ├── recommendations.py          ← existing (untouched)
│       └── coaching.py                 ← NEW
├── notification_module/
│   ├── models/notification_preference.py  ← EXTENDED: coaching_reminders_enabled, coaching_daily_hour
│   ├── tasks.py                           ← EXTENDED: run_daily_coaching, run_weekly_coaching
│   └── ...
└── celery_app.py                          ← EXTENDED: daily-coaching + weekly-coaching beat entries
```

## How It Works

### Daily Coaching (hourly Celery beat, filtered by user's preferred hour)

```
Celery beat → run_daily_coaching task
    ↓
For each user with coaching_reminders_enabled + matching hour:
    ↓
Call RecommendationService.get_daily_suggestion(user_id)
    → returns { urgency, suggestion } (existing feature engineering + LLM)
    ↓
If urgency == "on_track": skip (don't spam)
If urgency == "needs_attention" or "off_track":
    ├── Save to coaching_messages table (audit trail)
    └── Send push notification via existing Firebase push service
```

### Weekly Review (Celery beat, Sunday 09:00 UTC)

```
Celery beat → run_weekly_coaching task
    ↓
For each user with coaching_reminders_enabled:
    ↓
Call RecommendationService.get_progress_report(user_id, "week")
    → returns { features, assessment, improvements, suggestions } (existing)
    ↓
Save summary to coaching_messages table
Send push notification with assessment
```

## Endpoints

```
GET  /v1/coaching/status              → Real-time on-track check (daily suggestion + weekly features)
GET  /v1/coaching/messages             → List coaching messages (filter: category, unread_only)
PATCH /v1/coaching/messages/{id}/read  → Mark as read
POST /v1/coaching/messages/read-all    → Mark all as read
DELETE /v1/coaching/messages/{id}      → Dismiss
```

## Notification Preferences

Users control coaching via existing notification preferences:
- `coaching_reminders_enabled` (default: true)
- `coaching_daily_hour` (default: 20, UTC) — when to run the daily check

## Key Principles

1. **No feature duplication** — reuses existing `get_daily_suggestion()` and `get_progress_report()`
2. **Existing infrastructure** — Celery + Redis + Firebase already running
3. **Anti-spam** — only notifies when user is off track; on_track = silence
4. **Audit trail** — all sent messages persisted in `coaching_messages` table
5. **User control** — toggle + hour preference via notification settings
