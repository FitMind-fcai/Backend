import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.ai_services.ai_coach.ai_coach_service import AICoachService, get_ai_coach_service
from app.notification_module.models.notification_preference import NotificationPreference
from app.notification_module.repositories.device_token_repository import DeviceTokenRepository
from app.notification_module.repositories.notification_preference_repository import NotificationPreferenceRepository
from app.notification_module.services.push_service import send_push_multi
from app.planning_module.repositories.nutrition_repository import NutritionPlanRepository
from app.planning_module.repositories.workout_repository import WorkoutPlanRepository
from app.profile_module.repositories.profile_repository import ProfileRepository
from app.recommendation_system.models.coaching_message import CoachingMessage
from app.recommendation_system.repositories.coaching_message_repository import CoachingMessageRepository
from app.recommendation_system.services.recommendation_service import RecommendationService
from app.tracking_module.repositories.hydration_log_repository import HydrationLogRepository
from app.tracking_module.repositories.meal_log_repository import MealLogRepository
from app.tracking_module.repositories.sleep_log_repository import SleepLogRepository
from app.tracking_module.repositories.weight_log_repository import WeightLogRepository
from app.tracking_module.repositories.workout_log_repository import WorkoutLogRepository

logger = logging.getLogger(__name__)


class CoachingService:
    def __init__(self, db: Session, ai_coach: Optional[AICoachService] = None):
        self.db = db
        self.ai_coach = ai_coach or get_ai_coach_service()
        self.token_repo = DeviceTokenRepository(db)
        self.pref_repo = NotificationPreferenceRepository(db)
        self.message_repo = CoachingMessageRepository(db)

    def _build_recommendation_service(self) -> RecommendationService:
        return RecommendationService(
            meal_repo=MealLogRepository(self.db),
            workout_repo=WorkoutLogRepository(self.db),
            weight_repo=WeightLogRepository(self.db),
            sleep_repo=SleepLogRepository(self.db),
            hydration_repo=HydrationLogRepository(self.db),
            nutrition_plan_repo=NutritionPlanRepository(self.db),
            workout_plan_repo=WorkoutPlanRepository(self.db),
            profile_repo=ProfileRepository(self.db),
            ai_coach=self.ai_coach,
        )

    def _get_active_tokens(self, user_id: int) -> List[str]:
        return [t.token for t in self.token_repo.get_active_tokens_for_user(user_id)]

    # ── Daily coaching check ──────────────────────────────────────────────────

    def run_daily_coaching(self):
        now = datetime.now(timezone.utc)
        rec_service = self._build_recommendation_service()

        for pref in self.pref_repo.get_with_coaching_enabled():
            if now.hour != pref.coaching_daily_hour:
                continue

            user_id = pref.user_id
            try:
                suggestion = rec_service.get_daily_suggestion(user_id)
            except Exception as exc:
                logger.warning("Daily coaching failed for user %s: %s", user_id, exc)
                continue

            if suggestion.urgency == "on_track":
                continue

            title = self._daily_title(suggestion.urgency)
            body = suggestion.suggestion

            self.message_repo.create(
                user_id=user_id,
                category="daily",
                urgency=suggestion.urgency,
                title=title,
                body=body,
            )

            tokens = self._get_active_tokens(user_id)
            if tokens:
                send_push_multi(
                    tokens,
                    title,
                    body[:200],
                    {"type": "coaching", "urgency": suggestion.urgency},
                )

            logger.info(
                "Daily coaching sent to user %s — urgency=%s",
                user_id, suggestion.urgency,
            )

    # ── Weekly coaching review ────────────────────────────────────────────────

    def run_weekly_coaching(self):
        rec_service = self._build_recommendation_service()

        for pref in self.pref_repo.get_with_coaching_enabled():
            user_id = pref.user_id
            try:
                report = rec_service.get_progress_report(user_id, period="week")
            except Exception as exc:
                logger.warning("Weekly coaching failed for user %s: %s", user_id, exc)
                continue

            urgency = "on_track" if report.features.on_track else "needs_attention"
            title = "📊 Your Weekly Progress Report"

            parts = [report.assessment]
            if report.improvements:
                parts.append("Focus on: " + "; ".join(report.improvements[:2]))
            if report.suggestions:
                parts.append("Tip: " + report.suggestions[0])
            body = "\n".join(parts)

            self.message_repo.create(
                user_id=user_id,
                category="weekly",
                urgency=urgency,
                title=title,
                body=body,
            )

            tokens = self._get_active_tokens(user_id)
            if tokens:
                send_push_multi(
                    tokens,
                    title,
                    report.assessment[:200],
                    {"type": "coaching", "category": "weekly"},
                )

            logger.info("Weekly coaching sent to user %s — on_track=%s", user_id, report.features.on_track)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _daily_title(urgency: str) -> str:
        if urgency == "off_track":
            return "🚨 Coach Alert: You're Off Track"
        return "⚡ Coach Nudge: Needs Attention"
