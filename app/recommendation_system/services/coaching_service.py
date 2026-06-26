import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.ai_services.ai_coach.ai_coach_service import AICoachService, get_ai_coach_service
from app.notification_module.repositories.device_token_repository import DeviceTokenRepository
from app.notification_module.repositories.notification_preference_repository import NotificationPreferenceRepository
from app.notification_module.services.push_service import send_push_multi
from app.planning_module.repositories.nutrition_repository import NutritionPlanRepository
from app.planning_module.repositories.workout_repository import WorkoutPlanRepository
from app.profile_module.repositories.profile_repository import ProfileRepository
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

    def _send_and_persist(self, user_id: int, category: str, urgency: str,
                          title: str, body: str, push_data: dict) -> dict:
        msg = self.message_repo.create(
            user_id=user_id,
            category=category,
            urgency=urgency,
            title=title,
            body=body,
        )
        push_count = 0
        tokens = self._get_active_tokens(user_id)
        if tokens:
            push_count = send_push_multi(tokens, title, body[:200], push_data, db=self.db)

        return {
            "message_id": msg.id,
            "urgency": urgency,
            "title": title,
            "body": body,
            "push_sent_to": len(tokens),
            "push_delivered": push_count,
        }

    # ── Trigger endpoints (instant, bypasses schedule) ───────────────────────

    def trigger_daily_for_user(self, user_id: int) -> dict:
        rec_service = self._build_recommendation_service()
        suggestion = rec_service.get_daily_suggestion(user_id)

        title = self._daily_title(suggestion.urgency)
        result = self._send_and_persist(
            user_id, "daily", suggestion.urgency,
            title, suggestion.suggestion,
            {"type": "coaching", "urgency": suggestion.urgency},
        )
        return result

    def trigger_weekly_for_user(self, user_id: int) -> dict:
        rec_service = self._build_recommendation_service()
        report = rec_service.get_progress_report(user_id, period="week")

        urgency = "on_track" if report.features.on_track else "needs_attention"
        title = "📊 Your Weekly Progress Report"

        parts = [report.assessment]
        if report.improvements:
            parts.append("Focus on: " + "; ".join(report.improvements[:2]))
        if report.suggestions:
            parts.append("Tip: " + report.suggestions[0])
        body = "\n".join(parts)

        result = self._send_and_persist(
            user_id, "weekly", urgency,
            title, body,
            {"type": "coaching", "category": "weekly"},
        )
        result["on_track"] = report.features.on_track
        result["overall_score"] = report.features.overall_consistency_score
        return result

    # ── Batch coaching (called by Celery tasks) ──────────────────────────────

    def run_daily_coaching(self):
        rec_service = self._build_recommendation_service()

        for pref in self.pref_repo.get_with_coaching_enabled():
            user_id = pref.user_id
            try:
                suggestion = rec_service.get_daily_suggestion(user_id)
            except Exception as exc:
                logger.warning("Daily coaching failed for user %s: %s", user_id, exc)
                continue

            if suggestion.urgency == "on_track":
                continue

            title = self._daily_title(suggestion.urgency)
            self._send_and_persist(
                user_id, "daily", suggestion.urgency,
                title, suggestion.suggestion,
                {"type": "coaching", "urgency": suggestion.urgency},
            )
            logger.info("Daily coaching sent to user %s — urgency=%s", user_id, suggestion.urgency)

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

            self._send_and_persist(
                user_id, "weekly", urgency,
                title, body,
                {"type": "coaching", "category": "weekly"},
            )
            logger.info("Weekly coaching sent to user %s — on_track=%s", user_id, report.features.on_track)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _daily_title(urgency: str) -> str:
        if urgency == "off_track":
            return "🚨 Coach Alert: You're Off Track"
        return "⚡ Coach Nudge: Needs Attention"
