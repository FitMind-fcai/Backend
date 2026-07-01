"""
Integration tests for /v1/profile/* routes.
"""
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from app.profile_module.schemas.profile import ProfileResponse
from datetime import datetime


def _make_profile_response():
    """Build a realistic ProfileResponse-compatible object."""
    p = MagicMock()
    p.id = 1
    p.user_id = 1
    p.age = 28
    p.gender = "Male"
    p.height = 178.0
    p.weight = 75.0
    p.fitness_goal = "Lose Weight"
    p.activity_level = "Moderately Active"
    p.dietary_preference = "None"
    p.medical_conditions = "None"
    p.allergies = "None"
    p.injuries = "None"
    p.medications = "None"
    p.updated_at = None
    return p


VALID_PAYLOAD = {
    "user_id": 1,
    "age": 28,
    "gender": "Male",
    "height": 178.0,
    "weight": 75.0,
    "fitness_goal": "Lose Weight",
    "activity_level": "Moderately Active",
    "dietary_preference": "None",
    "medical_conditions": "None",
    "allergies": "None",
    "injuries": "None",
    "medications": "None",
}


class TestGetProfile:
    def test_returns_200_with_profile_data(self, client, headers, mock_profile):
        mock_profile.get_profile.return_value = _make_profile_response()
        resp = client.get("/v1/profile", headers=headers)
        assert resp.status_code == 200

    def test_no_profile_returns_404(self, client, headers, mock_profile):
        mock_profile.get_profile.side_effect = HTTPException(status_code=404, detail="Not found")
        resp = client.get("/v1/profile", headers=headers)
        assert resp.status_code == 404

    def test_unauthenticated_returns_401_or_403(self, client):
        resp = client.get("/v1/profile")
        assert resp.status_code in (401, 403)


class TestCreateProfile:
    def test_valid_profile_creates_successfully(self, client, headers, mock_profile):
        mock_profile.create_profile.return_value = _make_profile_response()
        resp = client.post("/v1/profile", json=VALID_PAYLOAD, headers=headers)
        assert resp.status_code in (200, 201)

    def test_invalid_gender_returns_422(self, client, headers):
        bad = {**VALID_PAYLOAD, "gender": "Unknown"}
        resp = client.post("/v1/profile", json=bad, headers=headers)
        assert resp.status_code == 422

    def test_invalid_activity_level_returns_422(self, client, headers):
        bad = {**VALID_PAYLOAD, "activity_level": "Ultra Active"}
        resp = client.post("/v1/profile", json=bad, headers=headers)
        assert resp.status_code == 422


class TestUpdateProfile:
    def test_partial_update_succeeds(self, client, headers, mock_profile):
        mock_profile.update_profile.return_value = _make_profile_response()
        resp = client.patch("/v1/profile", json={"user_id": 1, "age": 30}, headers=headers)
        assert resp.status_code == 200

    def test_invalid_field_value_returns_422(self, client, headers):
        resp = client.patch("/v1/profile", json={"user_id": 1, "fitness_goal": "Fly to Moon"}, headers=headers)
        assert resp.status_code == 422
