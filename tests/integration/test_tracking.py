"""
Integration tests for /v1/tracking/* routes.
"""
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException

from app.tracking_module.schemas.tracking import SaveLogsResponse


class TestSaveLogs:
    MEAL_PAYLOAD = {
        "category": "meal",
        "log_date": "2024-01-15",
        "log_method": "TEXT",
        "meal_entries": [
            {"central_food_id": 123, "meal_type": "Lunch", "servings": 1.0}
        ],
    }

    def test_save_meal_log_returns_201(self, client, headers, mock_tracking):
        mock_tracking.save_logs.return_value = SaveLogsResponse(category="meal", saved_count=1)
        resp = client.post("/v1/tracking/logs", json=self.MEAL_PAYLOAD, headers=headers)
        assert resp.status_code == 201

    def test_save_weight_log_returns_201(self, client, headers, mock_tracking):
        mock_tracking.save_logs.return_value = SaveLogsResponse(category="weight", saved_count=1)
        payload = {
            "category": "weight",
            "log_date": "2024-01-15",
            "log_method": "TEXT",
            "weight_entries": [{"weight": 75.5}],
        }
        resp = client.post("/v1/tracking/logs", json=payload, headers=headers)
        assert resp.status_code == 201

    def test_missing_category_returns_422(self, client, headers):
        resp = client.post("/v1/tracking/logs", json={"log_date": "2024-01-15"}, headers=headers)
        assert resp.status_code == 422

    def test_unauthenticated_returns_401_or_403(self, unauthenticated_client):
        resp = unauthenticated_client.post("/v1/tracking/logs", json=self.MEAL_PAYLOAD)
        assert resp.status_code in (401, 403)


class TestGetLogs:
    def test_get_meal_logs_returns_list(self, client, headers, mock_tracking):
        mock_tracking.get_meal_logs.return_value = []
        resp = client.get("/v1/tracking/logs/meals", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_workout_logs_returns_list(self, client, headers, mock_tracking):
        mock_tracking.get_workout_logs.return_value = []
        resp = client.get("/v1/tracking/logs/workouts", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_weight_logs_returns_list(self, client, headers, mock_tracking):
        mock_tracking.get_weight_logs.return_value = []
        resp = client.get("/v1/tracking/logs/weights", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_date_filter_is_accepted(self, client, headers, mock_tracking):
        mock_tracking.get_meal_logs.return_value = []
        resp = client.get("/v1/tracking/logs/meals?date=2024-01-15", headers=headers)
        assert resp.status_code == 200

    def test_invalid_date_format_returns_422(self, client, headers):
        resp = client.get("/v1/tracking/logs/meals?date=not-a-date", headers=headers)
        assert resp.status_code == 422


class TestFoodSearch:
    def test_search_returns_list(self, client, headers, mock_tracking):
        mock_tracking.search_foods.return_value = []
        resp = client.get("/v1/tracking/meals/search?q=chicken", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_short_query_returns_422(self, client, headers):
        resp = client.get("/v1/tracking/meals/search?q=a", headers=headers)
        assert resp.status_code == 422

    def test_missing_query_param_returns_422(self, client, headers):
        resp = client.get("/v1/tracking/meals/search", headers=headers)
        assert resp.status_code == 422


class TestDeleteLog:
    def test_delete_meal_log_returns_204(self, client, headers, mock_tracking):
        mock_tracking.delete_log.return_value = None
        resp = client.delete("/v1/tracking/logs/meal/1", headers=headers)
        assert resp.status_code == 204

    def test_delete_unknown_returns_4xx(self, client, headers, mock_tracking):
        mock_tracking.delete_log.side_effect = HTTPException(status_code=404, detail="Not found")
        resp = client.delete("/v1/tracking/logs/meal/9999", headers=headers)
        assert resp.status_code in (400, 404)
