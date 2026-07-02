"""
Unit tests for CoachingService's weekly-report delivery split:
  - push notification carries only a short on_track/needs_attention summary
  - the full report (positives/improvements/suggestions/projection) goes out by email
"""
from unittest.mock import MagicMock

import pytest

from app.recommendation_system.schemas.recommendations import (
    NutritionFeatures,
    ProgressFeatures,
    ProgressReport,
    WeightFeatures,
    WorkoutFeatures,
)
from app.recommendation_system.services.coaching_service import CoachingService


def _make_report(on_track: bool) -> ProgressReport:
    features = ProgressFeatures(
        period_label="Last 7 Days",
        period_days=7,
        period_start="2026-06-25",
        period_end="2026-07-02",
        user_goal="Lose Weight",
        overall_consistency_score=0.8 if on_track else 0.4,
        on_track=on_track,
        nutrition=NutritionFeatures(
            period_days=7, days_with_logs=6, logging_consistency_pct=85.0,
            avg_daily_calories=1800.0, target_daily_calories=1800,
            calorie_adherence_pct=95.0, avg_daily_protein_g=130.0,
            target_daily_protein_g=140, protein_adherence_pct=92.0,
            avg_daily_carbs_g=180.0, avg_daily_fats_g=60.0,
            calorie_trend_slope=0.0, macro_balance_score=88.0,
        ),
        workout=WorkoutFeatures(
            period_days=7, total_sessions=3, planned_sessions=4,
            frequency_adherence_pct=75.0, avg_sets_per_session=12.0,
            avg_reps_per_session=10.0, total_volume_kg=3000.0,
            volume_trend_slope=0.0, unique_exercises_count=8,
            exercise_progressions=[],
        ),
        weight=WeightFeatures(
            measurements_count=2, start_weight_kg=80.0, latest_weight_kg=79.5,
            weight_change_kg=-0.5, weight_trend_slope=-0.07,
            trend_direction="losing", goal_weight_kg=75.0,
        ),
    )
    return ProgressReport(
        features=features,
        assessment="Solid week overall.",
        positives=["Hit protein target most days"],
        improvements=["Missed one workout session"],
        suggestions=["Add a short walk on rest days"],
        projection="At this pace you'll reach your goal in ~10 weeks.",
        generated_at="2026-07-02T00:00:00",
    )


@pytest.fixture
def coaching_service():
    svc = CoachingService(db=MagicMock(), ai_coach=MagicMock())
    svc.user_repo = MagicMock()
    svc.token_repo = MagicMock()
    svc.pref_repo = MagicMock()
    svc.message_repo = MagicMock()
    svc.email_service = MagicMock()
    return svc


class TestWeeklyPushTitleBody:
    def test_on_track_title(self):
        title, body = CoachingService._weekly_push_title_body(_make_report(on_track=True))
        assert "On Track" in title
        assert "emailed" in body.lower()

    def test_needs_attention_title(self):
        title, body = CoachingService._weekly_push_title_body(_make_report(on_track=False))
        assert "Needs Attention" in title


class TestSendWeeklyReportEmail:
    def test_sends_email_with_status_in_subject(self, coaching_service):
        user = MagicMock(email="alice@example.com")
        coaching_service.user_repo.get_by_id.return_value = user
        coaching_service.email_service.send_email.return_value = True

        coaching_service._send_weekly_report_email(1, _make_report(on_track=True))

        coaching_service.email_service.send_email.assert_called_once()
        recipient, subject, html = coaching_service.email_service.send_email.call_args[0]
        assert recipient == "alice@example.com"
        assert "On Track" in subject
        assert "Solid week overall." in html
        assert "Add a short walk on rest days" in html

    def test_skips_when_user_has_no_email(self, coaching_service):
        coaching_service.user_repo.get_by_id.return_value = None
        coaching_service._send_weekly_report_email(1, _make_report(on_track=True))
        coaching_service.email_service.send_email.assert_not_called()


class TestTriggerWeeklyForUser:
    def test_sends_short_push_and_full_email(self, coaching_service):
        report = _make_report(on_track=False)
        rec_service = MagicMock()
        rec_service.get_progress_report.return_value = report
        coaching_service._build_recommendation_service = MagicMock(return_value=rec_service)
        coaching_service.message_repo.create.return_value = MagicMock(id=42)
        coaching_service.token_repo.get_active_tokens_for_user.return_value = []
        coaching_service.user_repo.get_by_id.return_value = MagicMock(email="bob@example.com")

        result = coaching_service.trigger_weekly_for_user(user_id=7)

        # Push/persisted message is the short summary, not the full report text
        create_kwargs = coaching_service.message_repo.create.call_args.kwargs
        assert create_kwargs["body"] == "Your full weekly progress report has been emailed to you — check your inbox."
        assert "Needs Attention" in create_kwargs["title"]

        # Full report went out by email
        coaching_service.email_service.send_email.assert_called_once()

        assert result["on_track"] is False
        assert result["overall_score"] == 0.4
