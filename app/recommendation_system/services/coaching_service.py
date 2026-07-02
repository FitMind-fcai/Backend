import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.ai_services.ai_coach.ai_coach_service import AICoachService, get_ai_coach_service
from app.auth_module.repositories.user_repository import UserRepository
from app.notification_module.repositories.device_token_repository import DeviceTokenRepository
from app.notification_module.repositories.notification_preference_repository import NotificationPreferenceRepository
from app.notification_module.services.push_service import send_push_multi
from app.planning_module.repositories.nutrition_repository import NutritionPlanRepository
from app.planning_module.repositories.workout_repository import WorkoutPlanRepository
from app.profile_module.repositories.profile_repository import ProfileRepository
from app.recommendation_system.repositories.coaching_message_repository import CoachingMessageRepository
from app.recommendation_system.schemas.recommendations import ProgressReport
from app.recommendation_system.services.recommendation_service import RecommendationService
from app.shared.services.email_service import EmailService
from app.shared.services.email_templates import render_email
from app.tracking_module.repositories.hydration_log_repository import HydrationLogRepository
from app.tracking_module.repositories.meal_log_repository import MealLogRepository
from app.tracking_module.repositories.sleep_log_repository import SleepLogRepository
from app.tracking_module.repositories.weight_log_repository import WeightLogRepository
from app.tracking_module.repositories.workout_log_repository import WorkoutLogRepository

logger = logging.getLogger(__name__)


def _render_weekly_report_email_html(report: ProgressReport) -> str:
    f = report.features

    def _list_items(items: List[str]) -> str:
        if not items:
            return "<p style=\"color:#9ca3af;\">None noted this week.</p>"
        lis = "".join(f"<li style=\"margin-bottom:8px;\">{item}</li>" for item in items)
        return f"<ul style=\"padding-left:20px; margin:0 0 20px;\">{lis}</ul>"

    stat = lambda label, value: (
        f'<td align="center" style="padding:12px 8px;">'
        f'<div style="font-size:22px; font-weight:700; color:#111827;">{value}</div>'
        f'<div style="font-size:12px; color:#6b7280; margin-top:2px;">{label}</div>'
        f'</td>'
    )

    calorie_adherence = (
        f"{f.nutrition.calorie_adherence_pct:.0f}%" if f.nutrition.calorie_adherence_pct is not None else "—"
    )
    workout_adherence = (
        f"{f.workout.frequency_adherence_pct:.0f}%" if f.workout.frequency_adherence_pct is not None else "—"
    )

    body_html = f"""
        <p>{report.assessment}</p>

        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="background:#fff7ed; border-radius:12px; margin: 20px 0;">
          <tr>
            {stat("Overall Score", f"{f.overall_consistency_score * 100:.0f}%")}
            {stat("Calorie Adherence", calorie_adherence)}
            {stat("Workout Adherence", workout_adherence)}
          </tr>
        </table>

        <h3 style="color:#111827; font-size:16px; margin: 24px 0 8px;">✅ What's going well</h3>
        {_list_items(report.positives)}

        <h3 style="color:#111827; font-size:16px; margin: 24px 0 8px;">🎯 Areas to improve</h3>
        {_list_items(report.improvements)}

        <h3 style="color:#111827; font-size:16px; margin: 24px 0 8px;">💡 Suggestions for next week</h3>
        {_list_items(report.suggestions)}

        <p style="background:#f4f4f5; border-radius:10px; padding:14px 16px; margin-top: 20px;">
          <strong>Looking ahead:</strong> {report.projection}
        </p>
    """

    return render_email(
        heading="📊 Your Weekly Progress Report",
        preheader=f"{f.period_label}: {report.assessment[:100]}",
        body_html=body_html,
        footer_note=f"Report period: {f.period_start} to {f.period_end}.",
    )


class CoachingService:
    def __init__(self, db: Session, ai_coach: Optional[AICoachService] = None):
        self.db = db
        self.ai_coach = ai_coach or get_ai_coach_service()
        self.token_repo = DeviceTokenRepository(db)
        self.pref_repo = NotificationPreferenceRepository(db)
        self.message_repo = CoachingMessageRepository(db)
        self.user_repo = UserRepository(db)
        self.email_service = EmailService()

    def _send_weekly_report_email(self, user_id: int, report: ProgressReport) -> None:
        """Email the full weekly report (push notifications only carry a short summary)."""
        user = self.user_repo.get_by_id(user_id)
        if not user or not user.email:
            logger.warning("Weekly report email skipped for user %s — no email on file", user_id)
            return

        status_word = "On Track" if report.features.on_track else "Needs Attention"
        html = _render_weekly_report_email_html(report)
        sent = self.email_service.send_email(
            user.email,
            f"Your Weekly FitMind Report — {status_word}",
            html,
        )
        if not sent:
            logger.warning("Failed to send weekly report email to user %s", user_id)

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
        title, body = self._weekly_push_title_body(report)

        result = self._send_and_persist(
            user_id, "weekly", urgency,
            title, body,
            {"type": "coaching", "category": "weekly"},
        )
        self._send_weekly_report_email(user_id, report)

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
            title, body = self._weekly_push_title_body(report)

            self._send_and_persist(
                user_id, "weekly", urgency,
                title, body,
                {"type": "coaching", "category": "weekly"},
            )
            self._send_weekly_report_email(user_id, report)
            logger.info("Weekly coaching sent to user %s — on_track=%s", user_id, report.features.on_track)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _weekly_push_title_body(report: ProgressReport) -> tuple:
        """Short push/notification-list text — the full report goes out by email."""
        if report.features.on_track:
            title = "📊 Weekly Report: You're On Track!"
        else:
            title = "📊 Weekly Report: Needs Attention"
        body = "Your full weekly progress report has been emailed to you — check your inbox."
        return title, body

    @staticmethod
    def _daily_title(urgency: str) -> str:
        if urgency == "off_track":
            return "🚨 Coach Alert: You're Off Track"
        return "⚡ Coach Nudge: Needs Attention"
