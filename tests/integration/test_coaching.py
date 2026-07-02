"""
Integration tests for /v1/coaching/* routes.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from datetime import datetime


class TestCoachingStatus:
    def test_returns_status_object(self, client, headers, mock_recommendation):
        suggestion = MagicMock(urgency="on_track", suggestion="Keep it up!")
        report = MagicMock()
        report.features.overall_consistency_score = 85.0
        report.features.on_track = True
        report.features.nutrition.calorie_adherence_pct = 92.0
        report.features.workout.frequency_adherence_pct = 80.0

        mock_recommendation.get_daily_suggestion.return_value = suggestion
        mock_recommendation.get_progress_report.return_value = report

        resp = client.get("/v1/coaching/status", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "urgency" in body
        assert "on_track" in body
        assert "suggestion" in body

    def test_unauthenticated_returns_401_or_403(self, unauthenticated_client):
        resp = unauthenticated_client.get("/v1/coaching/status")
        assert resp.status_code in (401, 403)


class TestListMessages:
    def test_returns_message_list_with_unread_count(self, client, headers):
        with patch("app.recommendation_system.routes.coaching.CoachingMessageRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.list_for_user.return_value = []
            mock_repo.count_unread.return_value = 0
            resp = client.get("/v1/coaching/messages", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "messages" in body
        assert "unread_count" in body
        assert body["unread_count"] == 0

    def test_category_filter_query_param_accepted(self, client, headers):
        with patch("app.recommendation_system.routes.coaching.CoachingMessageRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.list_for_user.return_value = []
            mock_repo.count_unread.return_value = 0
            resp = client.get("/v1/coaching/messages?category=daily&unread_only=true", headers=headers)
        assert resp.status_code == 200


class TestMarkMessageRead:
    def test_existing_message_returns_200(self, client, headers):
        with patch("app.recommendation_system.routes.coaching.CoachingMessageRepository") as MockRepo:
            mock_msg = MagicMock()
            mock_msg.id = 1
            mock_msg.user_id = 1
            mock_msg.category = "daily"
            mock_msg.urgency = "on_track"
            mock_msg.title = "Test"
            mock_msg.body = "Body"
            mock_msg.is_read = True
            mock_msg.is_dismissed = False
            mock_msg.created_at = datetime.utcnow()
            MockRepo.return_value.mark_read.return_value = mock_msg
            resp = client.patch("/v1/coaching/messages/1/read", headers=headers)
        assert resp.status_code == 200

    def test_nonexistent_message_returns_404(self, client, headers):
        with patch("app.recommendation_system.routes.coaching.CoachingMessageRepository") as MockRepo:
            MockRepo.return_value.mark_read.return_value = None
            resp = client.patch("/v1/coaching/messages/9999/read", headers=headers)
        assert resp.status_code == 404


class TestTriggerCoaching:
    def test_trigger_daily_returns_result(self, client, headers):
        with patch("app.recommendation_system.routes.coaching.CoachingService") as MockSvc:
            MockSvc.return_value.trigger_daily_for_user.return_value = {
                "message_id": 1, "urgency": "needs_attention",
                "title": "Coach Nudge", "body": "Work out today!",
                "push_sent_to": 0, "push_delivered": 0,
            }
            resp = client.post("/v1/coaching/trigger/daily", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "message_id" in body
        assert "urgency" in body

    def test_trigger_weekly_returns_result(self, client, headers):
        with patch("app.recommendation_system.routes.coaching.CoachingService") as MockSvc:
            MockSvc.return_value.trigger_weekly_for_user.return_value = {
                "message_id": 2, "urgency": "on_track",
                "title": "Weekly Report", "body": "Great week!",
                "push_sent_to": 0, "push_delivered": 0,
            }
            resp = client.post("/v1/coaching/trigger/weekly", headers=headers)
        assert resp.status_code == 200
