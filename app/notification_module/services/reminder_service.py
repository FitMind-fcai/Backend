import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Tuple

from sqlalchemy.orm import Session

from app.notification_module.models.notification_preference import NotificationPreference
from app.notification_module.repositories.device_token_repository import DeviceTokenRepository
from app.notification_module.repositories.notification_preference_repository import NotificationPreferenceRepository
from app.notification_module.services.push_service import send_push_multi
from app.planning_module.repositories.nutrition_repository import NutritionPlanRepository
from app.planning_module.repositories.workout_repository import WorkoutPlanRepository
from app.tracking_module.repositories.hydration_log_repository import HydrationLogRepository
from app.tracking_module.repositories.meal_log_repository import MealLogRepository
from app.tracking_module.repositories.sleep_log_repository import SleepLogRepository
from app.tracking_module.repositories.workout_log_repository import WorkoutLogRepository

logger = logging.getLogger(__name__)

# Canonical meal times (hour, minute) — same mapping used by recommendation service
_MEAL_TIMES: List[Tuple[str, Tuple[int, int]]] = [
    ("pre-workout",       (9,  30)),
    ("post-workout",      (16, 30)),
    ("morning snack",     (10, 30)),
    ("afternoon snack",   (16,  0)),
    ("evening snack",     (21,  0)),
    ("breakfast",         (7,  30)),
    ("lunch",             (13,  0)),
    ("dinner",            (19,  0)),
    ("snack",             (15,  0)),
]


def _meal_hour_minute(meal_type: str) -> Tuple[int, int]:
    lower = meal_type.lower()
    for keyword, hm in _MEAL_TIMES:
        if keyword in lower:
            return hm
    return (12, 0)


class ReminderService:
    def __init__(self, db: Session):
        self.db        = db
        self.token_repo = DeviceTokenRepository(db)
        self.pref_repo  = NotificationPreferenceRepository(db)

    # ── Internal helper ────────────────────────────────────────────────────────

    def _eligible(self, prefs: List[NotificationPreference]):
        """Yield (user_id, token_strings, pref) for users who have active device tokens."""
        for pref in prefs:
            tokens = [t.token for t in self.token_repo.get_active_tokens_for_user(pref.user_id)]
            if tokens:
                yield pref.user_id, tokens, pref

    # ── Instant triggers (bypass schedule, single user) ─────────────────────

    def trigger_hydration_for_user(self, user_id: int) -> dict:
        tokens = [t.token for t in self.token_repo.get_active_tokens_for_user(user_id)]
        title = "💧 Hydration Reminder"
        body = "This is a test hydration reminder — drink some water!"
        push_count = 0
        if tokens:
            push_count = send_push_multi(tokens, title, body) or 0
        return {"type": "hydration", "title": title, "body": body,
                "push_sent_to": len(tokens), "push_delivered": push_count}

    def trigger_sleep_for_user(self, user_id: int) -> dict:
        tokens = [t.token for t in self.token_repo.get_active_tokens_for_user(user_id)]
        title = "😴 Log Your Sleep"
        body = "Don't forget to log last night's sleep — it counts toward your FitMind Score!"
        push_count = 0
        if tokens:
            push_count = send_push_multi(tokens, title, body) or 0
        return {"type": "sleep", "title": title, "body": body,
                "push_sent_to": len(tokens), "push_delivered": push_count}

    def trigger_workout_for_user(self, user_id: int) -> dict:
        tokens = [t.token for t in self.token_repo.get_active_tokens_for_user(user_id)]
        title = "💪 Workout Time!"
        body = "This is a test workout reminder — time to get moving!"
        push_count = 0
        if tokens:
            push_count = send_push_multi(tokens, title, body) or 0
        return {"type": "workout", "title": title, "body": body,
                "push_sent_to": len(tokens), "push_delivered": push_count}

    def trigger_meal_for_user(self, user_id: int) -> dict:
        tokens = [t.token for t in self.token_repo.get_active_tokens_for_user(user_id)]
        title = "🍽️ Meal Reminder"
        body = "This is a test meal reminder — time to eat and log your meal!"
        push_count = 0
        if tokens:
            push_count = send_push_multi(tokens, title, body) or 0
        return {"type": "meal", "title": title, "body": body,
                "push_sent_to": len(tokens), "push_delivered": push_count}

    # ── Hydration ──────────────────────────────────────────────────────────────

    def send_hydration_reminders(self):
        now = datetime.now(timezone.utc)
        # Only run during waking hours (08:00–22:00 UTC)
        if not (8 <= now.hour < 22):
            return

        hydration_repo = HydrationLogRepository(self.db)
        today = now.date()

        for user_id, tokens, pref in self._eligible(self.pref_repo.get_with_hydration_enabled()):
            logs = hydration_repo.list_logs(user_id, skip=0, limit=1, log_date=today)

            if not logs:
                send_push_multi(
                    tokens,
                    "💧 Hydration Reminder",
                    "No water logged today — drink a glass now and stay on track!",
                )
                continue

            last_log_time = logs[0].created_at
            if last_log_time.tzinfo is None:
                last_log_time = last_log_time.replace(tzinfo=timezone.utc)

            hours_since = (now - last_log_time).total_seconds() / 3600
            if hours_since >= pref.hydration_interval_hours:
                send_push_multi(
                    tokens,
                    "💧 Time to Hydrate!",
                    f"It's been {int(hours_since)}h since your last water log. Stay hydrated!",
                )

    # ── Sleep ──────────────────────────────────────────────────────────────────

    def send_sleep_reminders(self):
        now = datetime.now(timezone.utc)
        sleep_repo = SleepLogRepository(self.db)
        yesterday  = now.date() - timedelta(days=1)

        for user_id, tokens, pref in self._eligible(self.pref_repo.get_with_sleep_enabled()):
            if now.hour != pref.sleep_reminder_hour:
                continue

            logs = sleep_repo.list_logs(user_id, skip=0, limit=1, log_date=yesterday)
            if not logs:
                send_push_multi(
                    tokens,
                    "😴 Log Your Sleep",
                    "Don't forget to log last night's sleep — it counts toward your FitMind Score!",
                )

    # ── Meals ──────────────────────────────────────────────────────────────────

    def send_meal_reminders(self):
        now  = datetime.now(timezone.utc)
        today = now.date()
        now_minutes = now.hour * 60 + now.minute

        meal_repo          = MealLogRepository(self.db)
        nutrition_plan_repo = NutritionPlanRepository(self.db)

        for user_id, tokens, pref in self._eligible(self.pref_repo.get_with_meal_enabled()):
            plan = nutrition_plan_repo.get_active_plan(user_id)
            if not plan or not plan.days:
                continue

            days_elapsed = (today - plan.start_date).days
            day_number   = days_elapsed % 7 + 1
            today_day    = next((d for d in plan.days if d.day_number == day_number), None)
            if not today_day or not today_day.meals:
                continue

            # Collect already-logged meal types for today
            logged_types = {
                (log.meal_type or "").lower()
                for log in meal_repo.list_logs(user_id, skip=0, limit=50, log_date=today)
            }

            for meal in today_day.meals:
                meal_type = (meal.meal_type or "").strip()
                if not meal_type or meal_type.lower() in logged_types:
                    continue

                h, m = _meal_hour_minute(meal_type)
                meal_minutes = h * 60 + m
                window_start = meal_minutes - pref.meal_reminder_minutes_before

                # Fire only within the reminder window, not after meal time
                if window_start <= now_minutes < meal_minutes:
                    send_push_multi(
                        tokens,
                        f"🍽️ {meal_type.title()} Coming Up!",
                        f"{meal.meal_name} is on your plan — time to prepare!",
                        {"meal_type": meal_type, "meal_name": meal.meal_name},
                    )

    # ── Workouts ───────────────────────────────────────────────────────────────

    def send_workout_reminders(self):
        now   = datetime.now(timezone.utc)
        today = now.date()

        workout_repo      = WorkoutLogRepository(self.db)
        workout_plan_repo = WorkoutPlanRepository(self.db)

        for user_id, tokens, pref in self._eligible(self.pref_repo.get_with_workout_enabled()):
            if now.hour != pref.workout_reminder_hour:
                continue

            plan = workout_plan_repo.get_active_plan(user_id)
            if not plan or not plan.workout_days:
                continue

            days_elapsed = (today - plan.start_date).days
            day_number   = days_elapsed % len(plan.workout_days) + 1
            today_day    = next((d for d in plan.workout_days if d.day_number == day_number), None)
            if not today_day:
                continue

            logs = workout_repo.list_logs(user_id, skip=0, limit=1, log_date=today)
            if logs:
                continue  # already logged today

            send_push_multi(
                tokens,
                "💪 Workout Time!",
                f"Today is {today_day.day_name} — get moving and crush your session!",
                {"day_name": today_day.day_name, "focus": today_day.focus_area or ""},
            )
