# Coaching Engine — Implementation Plan (v2)

## Architecture Decision: Extend recommendation_system

The coaching engine is a **thin rules + scheduling layer** on top of existing feature engineering.
It does NOT duplicate any logic — it calls `RecommendationService` methods that already compute
everything (calorie adherence, weight trends, workout completion, sleep, hydration).

No new module. No Celery. No Redis. No daily snapshot table.

```
app/
├── recommendation_system/
│   ├── services/
│   │   ├── recommendation_service.py   ← existing feature engineering (untouched)
│   │   └── coaching_service.py         ← NEW: rules engine + coaching logic
│   ├── models/
│   │   ├── coaching_message.py         ← NEW: messages sent to user
│   │   └── plan_adjustment.py          ← NEW: proposed plan changes
│   ├── repositories/
│   │   ├── coaching_message_repository.py  ← NEW
│   │   └── plan_adjustment_repository.py   ← NEW
│   ├── routes/
│   │   ├── recommendations.py          ← existing endpoints (untouched)
│   │   └── coaching.py                 ← NEW: coaching endpoints
│   ├── schemas/
│   │   ├── recommendations.py          ← existing schemas (untouched)
│   │   └── coaching.py                 ← NEW: coaching schemas
│   └── core/
│       ├── dependencies.py             ← extend with coaching DI
│       └── constants.py                ← NEW: thresholds and rules config
```

---

## Why No Celery / No Redis / No Snapshots

### No Daily Snapshot Table

The existing feature engineering already aggregates tracking logs on-the-fly:

| What I Proposed (v1) | What Already Exists |
|---|---|
| `DailySnapshot.calories_actual` | `_engineer_nutrition_features()` → groups meal_logs by date, sums calories |
| `DailySnapshot.workout_done` | `_engineer_workout_features()` → `session_dates = set(log.log_date)` |
| `DailySnapshot.weight_kg` | `_engineer_weight_features()` → `sorted(logs, key=log_date)` |
| `DailySnapshot.water_ml` | `get_fitmind_score()` → `days_with_hydration[log.log_date] += water_ml` |
| `DailySnapshot.sleep_hours` | `get_fitmind_score()` → sleep scoring from sleep_logs |

Storing snapshots would just duplicate what these methods already compute from raw logs.
The raw logs ARE the source of truth — compute features on demand, don't cache them in a parallel table.

### No Celery / No Redis

At your current scale (<1000 users), a background task queue is overkill.
Instead, use **APScheduler** running inside the FastAPI process — zero extra services, zero extra cost.

```python
# app/core/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# Register in main.py on startup
@app.on_event("startup")
async def start_scheduler():
    from app.recommendation_system.services.coaching_service import CoachingService
    scheduler.add_job(CoachingService.run_nightly_check, "cron", hour=0, minute=30)
    scheduler.add_job(CoachingService.run_weekly_review, "cron", day_of_week="sun", hour=8)
    scheduler.start()
```

One process, one deployment, same Railway service. When you outgrow this (10K+ users),
migrate to Celery — but that's a scaling problem, not a design problem.

---

## How It Works (Reusing Existing Features)

### The Coaching Check Flow

```
Scheduler triggers (nightly or weekly)
    ↓
For each user with an active plan:
    ↓
Call EXISTING feature engineering:
    ├── recommendation_service._engineer_nutrition_features(user_id, since, until, period_days)
    │   → NutritionFeatures { calorie_adherence_pct, protein_adherence_pct, logging_consistency_pct, ... }
    ├── recommendation_service._engineer_workout_features(user_id, since, until, period_days)
    │   → WorkoutFeatures { frequency_adherence_pct, volume_trend_slope, ... }
    ├── recommendation_service._engineer_weight_features(user_id, since, until)
    │   → WeightFeatures { weight_change_kg, trend_direction, weight_trend_slope }
    └── recommendation_service._compute_overall_consistency(nutrition, workout, weight)
         → float (0.0–1.0)
    ↓
Pass features to StatusEvaluator (rules engine, no LLM)
    → UserStatus { overall, flags, urgency, action }
    ↓
Based on action:
    ├── "stay_silent"  → log status, done
    ├── "nudge"        → template message (no LLM), save to coaching_messages
    ├── "coach"        → LLM call for personalized advice, save to coaching_messages
    └── "adjust_plan"  → LLM call for plan modification proposal, save to plan_adjustments
```

### What the Status Evaluator Receives (Existing Pydantic Models)

```python
# These already exist in recommendation_system/schemas/recommendations.py

class NutritionFeatures(BaseModel):
    days_with_logs: int
    logging_consistency_pct: float          # days_with_logs / period_days × 100
    avg_daily_calories: float
    avg_daily_protein_g: float
    avg_daily_carbs_g: float
    avg_daily_fats_g: float
    calorie_adherence_pct: Optional[float]  # actual / target × 100
    protein_adherence_pct: Optional[float]
    calorie_trend_slope: float              # polyfit slope (rising/falling intake)
    macro_balance_score: float              # 0–100 how close to plan ratio

class WorkoutFeatures(BaseModel):
    total_sessions: int
    total_volume_kg: float
    avg_sets_per_session: float
    avg_reps_per_session: float
    unique_exercises_count: int
    frequency_adherence_pct: Optional[float]  # actual / planned sessions × 100
    volume_trend_slope: float                 # weekly volume trend
    exercise_progressions: List[ExerciseProgression]

class WeightFeatures(BaseModel):
    start_weight_kg: Optional[float]
    latest_weight_kg: Optional[float]
    weight_change_kg: float
    weight_trend_slope: float               # kg/day slope
    trend_direction: str                    # "losing" | "gaining" | "stable" | "no_data"
```

The coaching engine just applies rules to these — zero duplication.

---

## Phase 1: Status Evaluator (Rules Engine)

### 1.1 — Constants / Thresholds

```python
# recommendation_system/core/constants.py

COACHING_RULES = {
    # ── Engagement ──
    "DAYS_SILENT_BEFORE_NUDGE": 3,
    "MIN_LOGGING_CONSISTENCY_PCT": 50.0,

    # ── Nutrition ──
    "CALORIE_ADHERENCE_OK_MIN": 85.0,       # 85-115% = on track
    "CALORIE_ADHERENCE_OK_MAX": 115.0,
    "CALORIE_ADHERENCE_WARN_MIN": 70.0,     # 70-130% = drifting
    "CALORIE_ADHERENCE_WARN_MAX": 130.0,
    "PROTEIN_ADHERENCE_MIN_PCT": 80.0,

    # ── Weight (per week) ──
    "WEIGHT_LOSS_MIN_KG_WEEK": 0.20,
    "WEIGHT_LOSS_MAX_KG_WEEK": 1.20,
    "WEIGHT_GAIN_MIN_KG_WEEK": 0.15,
    "WEIGHT_GAIN_MAX_KG_WEEK": 0.60,
    "PLATEAU_MIN_WEEKS": 2,

    # ── Workouts ──
    "WORKOUT_ADHERENCE_OK_PCT": 80.0,
    "WORKOUT_ADHERENCE_WARN_PCT": 50.0,

    # ── Sleep ──
    "SLEEP_MIN_HOURS": 6.0,

    # ── Hydration ──
    "WATER_MIN_ML": 2000,

    # ── Coaching frequency ──
    "MAX_NUDGES_PER_DAY": 1,
    "MAX_COACHING_MESSAGES_PER_WEEK": 2,
}
```

### 1.2 — Status Evaluator

Takes the EXISTING feature objects, returns a coaching verdict.

```python
# recommendation_system/services/coaching_service.py

class UserStatus(BaseModel):
    overall: str          # "on_track" | "slight_drift" | "off_track" | "plateau" | "inactive"
    flags: list[str]      # what specifically is wrong
    urgency: str          # "none" | "low" | "medium" | "high"
    action: str           # "stay_silent" | "nudge" | "coach" | "adjust_plan"

def evaluate_status(
    nutrition: NutritionFeatures,
    workout: WorkoutFeatures,
    weight: WeightFeatures,
    user_goal: str,
    overall_consistency: float,
) -> UserStatus:
    """
    Pure rules — no LLM, no DB calls.
    Input: existing feature objects from RecommendationService.
    Output: coaching verdict.
    """
    flags = []

    # ── Engagement ──
    if nutrition.logging_consistency_pct < COACHING_RULES["MIN_LOGGING_CONSISTENCY_PCT"]:
        flags.append("low_logging_consistency")

    # ── Nutrition ──
    if nutrition.calorie_adherence_pct is not None:
        if nutrition.calorie_adherence_pct < COACHING_RULES["CALORIE_ADHERENCE_WARN_MIN"]:
            flags.append("severely_under_eating")
        elif nutrition.calorie_adherence_pct < COACHING_RULES["CALORIE_ADHERENCE_OK_MIN"]:
            flags.append("under_eating")
        elif nutrition.calorie_adherence_pct > COACHING_RULES["CALORIE_ADHERENCE_WARN_MAX"]:
            flags.append("severely_over_eating")
        elif nutrition.calorie_adherence_pct > COACHING_RULES["CALORIE_ADHERENCE_OK_MAX"]:
            flags.append("over_eating")

    if (nutrition.protein_adherence_pct is not None
            and nutrition.protein_adherence_pct < COACHING_RULES["PROTEIN_ADHERENCE_MIN_PCT"]):
        flags.append("low_protein")

    # ── Weight trend (goal-specific) ──
    if weight.trend_direction != "no_data":
        weekly_change = weight.weight_trend_slope * 7  # slope is kg/day → kg/week

        if user_goal == "lose_weight":
            if weekly_change > 0.05:
                flags.append("gaining_weight_on_cut")
            elif abs(weekly_change) < COACHING_RULES["WEIGHT_LOSS_MIN_KG_WEEK"]:
                flags.append("weight_plateau")
            elif abs(weekly_change) > COACHING_RULES["WEIGHT_LOSS_MAX_KG_WEEK"]:
                flags.append("losing_too_fast")

        elif user_goal == "build_muscle":
            if weekly_change < COACHING_RULES["WEIGHT_GAIN_MIN_KG_WEEK"]:
                flags.append("not_gaining_enough")
            elif weekly_change > COACHING_RULES["WEIGHT_GAIN_MAX_KG_WEEK"]:
                flags.append("gaining_too_fast")

    # ── Workouts ──
    if workout.frequency_adherence_pct is not None:
        if workout.frequency_adherence_pct < COACHING_RULES["WORKOUT_ADHERENCE_WARN_PCT"]:
            flags.append("missing_most_workouts")
        elif workout.frequency_adherence_pct < COACHING_RULES["WORKOUT_ADHERENCE_OK_PCT"]:
            flags.append("missing_some_workouts")

    # ── Determine overall status + action ──
    if not flags:
        return UserStatus(overall="on_track", flags=[], urgency="none", action="stay_silent")

    high_severity = {"gaining_weight_on_cut", "severely_under_eating", "severely_over_eating",
                     "losing_too_fast", "missing_most_workouts"}
    plan_change = {"weight_plateau", "gaining_weight_on_cut", "losing_too_fast"}

    has_high = any(f in high_severity for f in flags)
    needs_plan_change = any(f in plan_change for f in flags)

    if needs_plan_change:
        return UserStatus(overall="plateau" if "weight_plateau" in flags else "off_track",
                          flags=flags, urgency="high", action="adjust_plan")
    elif has_high:
        return UserStatus(overall="off_track", flags=flags, urgency="medium", action="coach")
    else:
        return UserStatus(overall="slight_drift", flags=flags, urgency="low", action="nudge")
```

---

## Phase 2: Coaching Service (Orchestrator)

### 2.1 — CoachingService

Ties together feature engineering → status evaluation → action.

```python
# recommendation_system/services/coaching_service.py

class CoachingService:
    def __init__(
        self,
        recommendation_service: RecommendationService,  # existing, injected
        coaching_message_repo: CoachingMessageRepository,
        plan_adjustment_repo: PlanAdjustmentRepository,
        ai_coach_service: AICoachService,               # existing LLM client
    ):
        self.reco = recommendation_service
        self.msg_repo = coaching_message_repo
        self.adj_repo = plan_adjustment_repo
        self.ai = ai_coach_service

    def check_user(self, user_id: int, period_days: int = 7) -> UserStatus:
        """
        Reuses existing feature engineering — no new queries, no duplication.
        """
        until = date.today()
        since = until - timedelta(days=period_days)

        # Call EXISTING methods from RecommendationService
        nutrition = self.reco._engineer_nutrition_features(user_id, since, until, period_days)
        workout = self.reco._engineer_workout_features(user_id, since, until, period_days)
        weight = self.reco._engineer_weight_features(user_id, since, until)
        consistency = self.reco._compute_overall_consistency(nutrition, workout, weight)
        user_goal = self.reco._user_goal(user_id)

        # Apply rules engine
        status = evaluate_status(nutrition, workout, weight, user_goal, consistency)
        return status

    def act_on_status(self, user_id: int, status: UserStatus,
                      nutrition: NutritionFeatures, workout: WorkoutFeatures,
                      weight: WeightFeatures):
        """
        Decide what to do based on status verdict.
        """
        if status.action == "stay_silent":
            return

        # Don't spam — check last message timestamp
        last_msg = self.msg_repo.get_latest_for_user(user_id)
        if last_msg and (datetime.utcnow() - last_msg.created_at).hours < 12:
            return

        if status.action == "nudge":
            self._send_template_nudge(user_id, status, nutrition, workout)

        elif status.action == "coach":
            self._send_llm_coaching(user_id, status, nutrition, workout, weight)

        elif status.action == "adjust_plan":
            self._propose_plan_adjustment(user_id, status, nutrition, workout, weight)

    def _send_template_nudge(self, user_id, status, nutrition, workout):
        """No LLM — pick from templates based on flags."""
        templates = {
            "under_eating": "You've been eating below your target this week. "
                            "Try adding a protein-rich snack to close the gap.",
            "low_protein": "Your protein is at {pct}% of target. "
                           "Consider adding eggs, chicken, or lentils to your meals.",
            "missing_some_workouts": "You completed {done} of your planned workouts. "
                                     "Even a short session counts — consistency beats intensity.",
            "low_logging_consistency": "You logged {days} out of 7 days this week. "
                                       "Logging helps your coach give better advice.",
        }
        # Pick first matching flag, fill template, save message
        ...

    def _send_llm_coaching(self, user_id, status, nutrition, workout, weight):
        """One LLM call — personalized advice based on features + flags."""
        prompt = f"""
        User status: {status.overall}
        Issues detected: {', '.join(status.flags)}

        Nutrition: {nutrition.calorie_adherence_pct}% calorie adherence,
                   {nutrition.protein_adherence_pct}% protein adherence,
                   trend slope: {nutrition.calorie_trend_slope}
        Workouts: {workout.frequency_adherence_pct}% adherence,
                  volume trend: {workout.volume_trend_slope}
        Weight:   {weight.weight_change_kg} kg change,
                  direction: {weight.trend_direction}

        Write a short (2-3 sentence) coaching message. Be specific and actionable.
        Don't repeat the numbers — give advice based on them.
        """
        # Call existing LLM client, save to coaching_messages
        ...

    def _propose_plan_adjustment(self, user_id, status, nutrition, workout, weight):
        """LLM proposes specific plan changes. User must approve."""
        # Similar to coaching but asks LLM for concrete changes
        # Saves to plan_adjustments with status="proposed"
        ...
```

### 2.2 — Scheduled Checks (APScheduler, no Celery)

```python
# recommendation_system/services/coaching_service.py

    @staticmethod
    async def run_nightly_check():
        """
        Lightweight check for ALL active users. No LLM.
        Only detects: user gone silent (3+ days no logs).
        """
        db = SessionLocal()
        try:
            active_users = get_users_with_active_plans(db)
            for user in active_users:
                last_log_date = get_last_log_date(db, user.id)
                days_silent = (date.today() - last_log_date).days if last_log_date else 999

                if days_silent >= COACHING_RULES["DAYS_SILENT_BEFORE_NUDGE"]:
                    # Check we haven't already nudged recently
                    already_nudged = check_recent_nudge(db, user.id, "inactive_nudge", days=3)
                    if not already_nudged:
                        save_coaching_message(db, user.id,
                            message_type="nudge",
                            trigger="inactive_3_days",
                            title="We miss you!",
                            body=f"You haven't logged anything in {days_silent} days. "
                                 "Even a quick meal log keeps you on track.")
        finally:
            db.close()

    @staticmethod
    async def run_weekly_review():
        """
        Full feature engineering + status evaluation for each active user.
        LLM called only for "coach" or "adjust_plan" actions.
        """
        db = SessionLocal()
        try:
            active_users = get_users_with_active_plans(db)
            for user in active_users:
                coaching = CoachingService(...)  # inject dependencies
                status = coaching.check_user(user.id, period_days=7)
                coaching.act_on_status(user.id, status, ...)
        finally:
            db.close()
```

---

## Phase 3: Models (Only 2 New Tables)

### 3.1 — Coaching Message

```python
# recommendation_system/models/coaching_message.py

class CoachingMessage(Base):
    __tablename__ = "coaching_messages"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    message_type = Column(String(50), nullable=False)
    # "weekly_summary" | "nudge" | "milestone" | "plan_adjustment_proposal" | "positive_reinforcement"

    trigger      = Column(String(100), nullable=False)
    # "weekly_review" | "inactive_3_days" | "plan_midpoint" | "plateau_detected"

    status_snapshot = Column(JSON, nullable=True)
    # { "overall": "off_track", "flags": ["low_protein"], "features": {...} }

    title        = Column(String(255), nullable=False)
    body         = Column(Text, nullable=False)

    is_read      = Column(Boolean, nullable=False, default=False)
    is_dismissed = Column(Boolean, nullable=False, default=False)

    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    read_at      = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_coaching_msg_user_unread", "user_id", "is_read"),
    )
```

### 3.2 — Plan Adjustment

```python
# recommendation_system/models/plan_adjustment.py

class PlanAdjustment(Base):
    __tablename__ = "coaching_plan_adjustments"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    coaching_message_id = Column(Integer, ForeignKey("coaching_messages.id"), nullable=True)

    adjustment_type  = Column(String(50), nullable=False)
    # "calorie_change" | "workout_frequency" | "exercise_swap" | "full_regeneration"

    plan_type        = Column(String(20), nullable=False)   # "nutrition" | "workout"
    plan_id          = Column(Integer, nullable=False)

    description      = Column(Text, nullable=False)
    changes_json     = Column(JSON, nullable=False)
    # { "daily_calories": { "old": 2200, "new": 2000 }, "reason": "2-week plateau" }

    status           = Column(String(20), nullable=False, default="proposed")
    # "proposed" | "approved" | "rejected"

    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at      = Column(DateTime(timezone=True), nullable=True)
```

---

## Phase 4: Endpoints

```
GET  /v1/coaching/messages?unread_only=true&limit=20
     → List coaching messages for current user

POST /v1/coaching/messages/{id}/read
     → Mark as read

POST /v1/coaching/messages/{id}/dismiss
     → Dismiss (won't show again)

GET  /v1/coaching/adjustments?status=proposed
     → List pending plan adjustment proposals

POST /v1/coaching/adjustments/{id}/approve
     → Apply the proposed changes to the plan

POST /v1/coaching/adjustments/{id}/reject
     → Reject with optional reason

GET  /v1/coaching/status
     → On-demand status check (calls feature engineering + rules engine)
     → { overall, flags, urgency, consistency_score, streak_days, last_review }
```

---

## Phase 5: Plan Milestone Checks

Triggered when a plan is created — schedule future checks relative to plan start date.

```
Plan created (day 0)
    → APScheduler: add jobs at day 7, 14, 21, 28

Day 7 (week 1 — adaptation period):
    → Lightweight: "How was your first week?" + basic stats
    → Low threshold — user is still adjusting to the plan

Day 14 (midpoint — most important):
    → Full feature analysis with 14 days of data
    → Plateau detection becomes meaningful here
    → Propose plan adjustment if trends are wrong

Day 21 (course correction):
    → Check if adjustment from day 14 is working
    → Generate new coaching advice if needed

Day 28 (plan end — retrospective):
    → Full retrospective: what worked, what didn't
    → Recommend next plan parameters
    → "You lost 2.1kg. For next month, let's increase workout frequency."
```

---

## Implementation Order

| Step | What | LLM? | Effort |
|------|------|------|--------|
| **1** | `constants.py` — thresholds and rules config | No | Small |
| **2** | `evaluate_status()` — rules engine function | No | Medium |
| **3** | `CoachingMessage` + `PlanAdjustment` models | No | Small |
| **4** | Repositories for new models | No | Small |
| **5** | `CoachingService.check_user()` — wires feature engineering → evaluator | No | Medium |
| **6** | Template nudge messages (no LLM) | No | Small |
| **7** | Coaching endpoints (messages, read, dismiss, status) | No | Medium |
| **8** | APScheduler setup + nightly check job | No | Small |
| **9** | Weekly review job + LLM coaching prompts | Yes | Large |
| **10** | Plan adjustment proposal + approve/reject flow | Yes | Large |
| **11** | Milestone check scheduling (triggered on plan creation) | Yes | Medium |

**Steps 1-8 = MVP** — rules-based coaching with template messages, no LLM cost.
**Steps 9-11 = AI coaching** — personalized advice and plan adjustment proposals.

---

## Cost

| Component | Monthly Cost (1000 users) |
|---|---|
| Nightly check (no LLM, just SQL) | $0 |
| Template nudges (no LLM) | $0 |
| Weekly review LLM calls (~30% of users need coaching) | ~$4/month |
| Plan adjustment proposals (~10% of users/week) | ~$2/month |
| APScheduler (runs inside existing FastAPI process) | $0 extra |
| **Total** | **~$6/month** |

---

## Key Principles

1. **No feature duplication** — the coaching engine consumes `NutritionFeatures`, `WorkoutFeatures`,
   `WeightFeatures` from the existing `RecommendationService`. All the math lives in one place.

2. **No new infrastructure** — APScheduler runs in-process. No Celery, no Redis, no extra
   Railway services. When you hit 10K+ users, migrate to Celery.

3. **Rules first, LLM second** — the status evaluator is pure Python math.
   The LLM only gets called when the coach needs to EXPLAIN something or PROPOSE a change.

4. **Never auto-apply** — plan adjustments are always proposals. The user approves or rejects.

5. **Anti-spam** — max 1 nudge per day, max 2 coaching messages per week.
   Good progress = silence (a real coach doesn't text you every day to say "good job").

6. **Consistent pattern** — follows the same models → repos → services → routes → schemas
   pattern as every other module in the codebase.
