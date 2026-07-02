"""
Unit tests for AuthService business logic.

All external dependencies (UserRepository, VerificationService,
AuthEmailService) are replaced with MagicMock — no database or network.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from app.auth_module.services.auth_service import AuthService
from app.auth_module.schemas.user import UserCreate, UserLogin
from app.auth_module.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_user_repo():
    repo = MagicMock()
    repo.email_exists.return_value = False
    repo.db = MagicMock()
    return repo


@pytest.fixture
def mock_verification_svc():
    svc = MagicMock()
    svc.create_verification_token.return_value = "verif-token-abc123"
    svc.validate_verification_token.return_value = "alice@example.com"
    return svc


@pytest.fixture
def mock_email_svc():
    svc = MagicMock()
    svc.send_verification_email.return_value = True
    return svc


@pytest.fixture
def auth_service(mock_user_repo, mock_verification_svc, mock_email_svc):
    return AuthService(
        user_repository=mock_user_repo,
        verification_service=mock_verification_svc,
        auth_email_service=mock_email_svc,
    )


@pytest.fixture
def sample_user():
    u = MagicMock(spec=User)
    u.id = 1
    u.name = "Alice"
    u.email = "alice@example.com"
    u.is_verified = True
    u.password = "$2b$12$fakehash"
    return u


# ---------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------

class TestCreateUser:
    def test_raises_400_when_email_already_registered(self, auth_service, mock_user_repo):
        mock_user_repo.email_exists.return_value = True
        with pytest.raises(HTTPException) as exc:
            auth_service.create_user(
                UserCreate(name="Alice", email="alice@example.com", password="pass123")
            )
        assert exc.value.status_code == 400

    def test_auto_verify_does_not_send_email(self, auth_service, mock_email_svc, mock_user_repo):
        with patch("app.auth_module.services.auth_service.hash_password", return_value="h"), \
             patch("app.auth_module.services.auth_service.User") as MockUser:
            MockUser.return_value = MagicMock(spec=User, id=1)
            _, token = auth_service.create_user(
                UserCreate(name="Bob", email="bob@example.com", password="pass123"),
                auto_verify=True,
            )
        assert token == ""
        mock_email_svc.send_verification_email.assert_not_called()

    def test_normal_signup_sends_verification_email(self, auth_service, mock_email_svc):
        with patch("app.auth_module.services.auth_service.hash_password", return_value="h"), \
             patch("app.auth_module.services.auth_service.User") as MockUser:
            MockUser.return_value = MagicMock(spec=User, id=2)
            _, token = auth_service.create_user(
                UserCreate(name="Carol", email="carol@example.com", password="pass123"),
                auto_verify=False,
            )
        mock_email_svc.send_verification_email.assert_called_once()
        assert token == "verif-token-abc123"

    def test_503_and_rollback_when_email_fails(self, auth_service, mock_user_repo, mock_email_svc):
        mock_email_svc.send_verification_email.return_value = False
        with patch("app.auth_module.services.auth_service.hash_password", return_value="h"), \
             patch("app.auth_module.services.auth_service.User") as MockUser:
            MockUser.return_value = MagicMock(spec=User, id=3)
            with pytest.raises(HTTPException) as exc:
                auth_service.create_user(
                    UserCreate(name="Dave", email="dave@example.com", password="pass123"),
                    auto_verify=False,
                )
        assert exc.value.status_code == 503
        mock_user_repo.db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# authenticate_user
# ---------------------------------------------------------------------------

class TestAuthenticateUser:
    def test_401_when_user_not_found(self, auth_service, mock_user_repo):
        mock_user_repo.get_by_email.return_value = None
        with pytest.raises(HTTPException) as exc:
            auth_service.authenticate_user(
                UserLogin(email="ghost@example.com", password="password")
            )
        assert exc.value.status_code == 401

    def test_401_when_wrong_password(self, auth_service, mock_user_repo, sample_user):
        mock_user_repo.get_by_email.return_value = sample_user
        with patch("app.auth_module.services.auth_service.verify_password", return_value=False):
            with pytest.raises(HTTPException) as exc:
                auth_service.authenticate_user(
                    UserLogin(email="alice@example.com", password="wrongpw")
                )
        assert exc.value.status_code == 401

    def test_403_when_account_not_verified(self, auth_service, mock_user_repo, sample_user):
        sample_user.is_verified = False
        mock_user_repo.get_by_email.return_value = sample_user
        with patch("app.auth_module.services.auth_service.verify_password", return_value=True):
            with pytest.raises(HTTPException) as exc:
                auth_service.authenticate_user(
                    UserLogin(email="alice@example.com", password="correct")
                )
        assert exc.value.status_code == 403

    def test_returns_user_and_token_on_success(self, auth_service, mock_user_repo, sample_user):
        mock_user_repo.get_by_email.return_value = sample_user
        with patch("app.auth_module.services.auth_service.verify_password", return_value=True), \
             patch("app.auth_module.services.auth_service.create_access_token", return_value="jwt-tok"):
            user, token = auth_service.authenticate_user(
                UserLogin(email="alice@example.com", password="correct")
            )
        assert user is sample_user
        assert token == "jwt-tok"


# ---------------------------------------------------------------------------
# get_user_by_email
# ---------------------------------------------------------------------------

class TestGetUserByEmail:
    def test_raises_404_when_not_found(self, auth_service, mock_user_repo):
        mock_user_repo.get_by_email.return_value = None
        with pytest.raises(HTTPException) as exc:
            auth_service.get_user_by_email("nobody@example.com")
        assert exc.value.status_code == 404

    def test_raises_403_for_unverified_when_flag_set(self, auth_service, mock_user_repo, sample_user):
        sample_user.is_verified = False
        mock_user_repo.get_by_email.return_value = sample_user
        with pytest.raises(HTTPException) as exc:
            auth_service.get_user_by_email("alice@example.com", require_verified=True)
        assert exc.value.status_code == 403

    def test_allows_unverified_without_flag(self, auth_service, mock_user_repo, sample_user):
        sample_user.is_verified = False
        mock_user_repo.get_by_email.return_value = sample_user
        result = auth_service.get_user_by_email("alice@example.com", require_verified=False)
        assert result is sample_user


# ---------------------------------------------------------------------------
# verify_user_email
# ---------------------------------------------------------------------------

class TestVerifyUserEmail:
    def test_raises_404_when_user_not_found_for_token(self, auth_service, mock_user_repo, mock_verification_svc):
        mock_user_repo.get_by_email.return_value = None
        with pytest.raises(HTTPException) as exc:
            auth_service.verify_user_email("some-token")
        assert exc.value.status_code == 404

    def test_marks_user_verified_and_deletes_token(self, auth_service, mock_user_repo, mock_verification_svc, sample_user):
        mock_user_repo.get_by_email.return_value = sample_user
        mock_user_repo.mark_as_verified.return_value = sample_user

        result = auth_service.verify_user_email("valid-token")

        mock_user_repo.mark_as_verified.assert_called_once_with(sample_user)
        mock_verification_svc.delete_verification_token.assert_called_once_with("valid-token")
        assert result is sample_user


# ---------------------------------------------------------------------------
# resend_verification
# ---------------------------------------------------------------------------

class TestResendVerification:
    def test_raises_404_when_user_not_found(self, auth_service, mock_user_repo):
        mock_user_repo.get_by_email.return_value = None
        with pytest.raises(HTTPException) as exc:
            auth_service.resend_verification("nobody@example.com")
        assert exc.value.status_code == 404

    def test_raises_400_when_already_verified(self, auth_service, mock_user_repo, sample_user):
        sample_user.is_verified = True
        mock_user_repo.get_by_email.return_value = sample_user
        with pytest.raises(HTTPException) as exc:
            auth_service.resend_verification("alice@example.com")
        assert exc.value.status_code == 400

    def test_returns_token_for_unverified_user(self, auth_service, mock_user_repo, mock_verification_svc, sample_user):
        sample_user.is_verified = False
        mock_user_repo.get_by_email.return_value = sample_user
        token = auth_service.resend_verification("alice@example.com")
        assert token == "verif-token-abc123"
