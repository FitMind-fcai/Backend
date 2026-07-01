"""
Integration tests for /v1/auth/* routes.

All external services are mocked; only HTTP routing and
request/response serialization are exercised here.
"""
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from app.auth_module.models.user import User


# ---------------------------------------------------------------------------
# POST /v1/auth/signup
# ---------------------------------------------------------------------------

class TestSignup:
    PAYLOAD = {"name": "Alice", "email": "alice@test.com", "password": "pass1234"}

    def test_successful_signup_returns_201(self, client, mock_auth, verified_user):
        mock_auth.create_user.return_value = (verified_user, "verif-token")
        resp = client.post("/v1/auth/signup", json=self.PAYLOAD)
        assert resp.status_code == 201

    def test_duplicate_email_returns_400(self, client, mock_auth):
        mock_auth.create_user.side_effect = HTTPException(status_code=400, detail="already registered")
        resp = client.post("/v1/auth/signup", json=self.PAYLOAD)
        assert resp.status_code == 400

    def test_missing_name_returns_422(self, client):
        resp = client.post("/v1/auth/signup", json={"email": "a@b.com", "password": "pass"})
        assert resp.status_code == 422

    def test_missing_password_returns_422(self, client):
        resp = client.post("/v1/auth/signup", json={"name": "A", "email": "a@b.com"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /v1/auth/login
# ---------------------------------------------------------------------------

class TestLogin:
    PAYLOAD = {"email": "alice@test.com", "password": "pass1234"}

    def test_successful_login_returns_200_with_token(self, client, mock_auth, verified_user):
        mock_auth.authenticate_user.return_value = (verified_user, "jwt-access-token")
        resp = client.post("/v1/auth/login", json=self.PAYLOAD)
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["access_token"] == "jwt-access-token"

    def test_wrong_password_returns_401(self, client, mock_auth):
        mock_auth.authenticate_user.side_effect = HTTPException(status_code=401, detail="Invalid credentials")
        resp = client.post("/v1/auth/login", json=self.PAYLOAD)
        assert resp.status_code == 401

    def test_missing_email_returns_422(self, client):
        resp = client.post("/v1/auth/login", json={"password": "pass1234"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /v1/auth/me
# ---------------------------------------------------------------------------

class TestGetMe:
    def test_authenticated_user_returns_200(self, client, headers, verified_user):
        resp = client.get("/v1/auth/me", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == verified_user.email

    def test_no_token_returns_403_or_401(self, client):
        resp = client.get("/v1/auth/me")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /v1/auth/forgot-password
# ---------------------------------------------------------------------------

class TestForgotPassword:
    def test_sends_otp_for_existing_user(self, client, mock_auth):
        mock_auth.get_user_by_email.return_value = MagicMock(spec=User, email="alice@test.com")
        resp = client.post("/v1/auth/forgot-password", json={"email": "alice@test.com"})
        assert resp.status_code == 200

    def test_unknown_email_returns_404(self, client, mock_auth):
        mock_auth.get_user_by_email.side_effect = HTTPException(status_code=404, detail="Not found")
        resp = client.post("/v1/auth/forgot-password", json={"email": "ghost@test.com"})
        assert resp.status_code == 404

    def test_missing_email_field_returns_422(self, client):
        resp = client.post("/v1/auth/forgot-password", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /v1/auth/verify-email
# ---------------------------------------------------------------------------

class TestVerifyEmail:
    def test_valid_token_returns_200(self, client, mock_auth, verified_user):
        mock_auth.verify_user_email.return_value = verified_user
        resp = client.post("/v1/auth/verify-email", json={"token": "valid-token-abc"})
        assert resp.status_code == 200

    def test_invalid_token_returns_4xx(self, client, mock_auth):
        mock_auth.verify_user_email.side_effect = HTTPException(status_code=400, detail="Invalid token")
        resp = client.post("/v1/auth/verify-email", json={"token": "bad-token"})
        assert resp.status_code in (400, 404, 422)
