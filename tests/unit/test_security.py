"""
Unit tests for app.core.security — password hashing, JWT tokens, secure token generation.
No database, no HTTP, no external services.
"""
import pytest
from jose import JWTError, jwt

from app.core.security import (
    create_access_token,
    generate_secure_token,
    hash_password,
    hash_string,
    verify_access_token,
    verify_hash,
    verify_password,
)
from app.core.config import JWT_SECRET_KEY, JWT_ALGORITHM


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_returns_string(self):
        assert isinstance(hash_password("mypassword"), str)

    def test_hash_differs_from_plaintext(self):
        pw = "mysecretpassword"
        assert hash_password(pw) != pw

    def test_correct_password_verifies(self):
        pw = "correcthorse"
        assert verify_password(pw, hash_password(pw)) is True

    def test_wrong_password_fails(self):
        hashed = hash_password("correcthorse")
        assert verify_password("batterystaple", hashed) is False

    def test_each_hash_uses_unique_salt(self):
        pw = "samepassword"
        assert hash_password(pw) != hash_password(pw)  # bcrypt random salt


# ---------------------------------------------------------------------------
# Generic string hashing (used for OTP tokens)
# ---------------------------------------------------------------------------

class TestGenericHashing:
    def test_hash_string_verifies_correctly(self):
        text = "my-otp-99991"
        assert verify_hash(text, hash_string(text)) is True

    def test_wrong_input_fails_verify(self):
        hashed = hash_string("correct")
        assert verify_hash("wrong", hashed) is False


# ---------------------------------------------------------------------------
# JWT access tokens
# ---------------------------------------------------------------------------

class TestJWT:
    def test_token_is_nonempty_string(self):
        token = create_access_token(1, "a@b.com")
        assert isinstance(token, str) and token

    def test_payload_has_correct_fields(self):
        token = create_access_token(42, "alice@fitmind.com")
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        assert payload["id"] == 42
        assert payload["email"] == "alice@fitmind.com"
        assert "exp" in payload

    def test_verify_valid_token_returns_payload(self):
        token = create_access_token(5, "bob@fitmind.com")
        payload = verify_access_token(token)
        assert payload["id"] == 5
        assert payload["email"] == "bob@fitmind.com"

    def test_tampered_token_raises_jwt_error(self):
        token = create_access_token(1, "a@b.com")
        with pytest.raises(JWTError):
            verify_access_token(token[:-3] + "ZZZ")

    def test_garbage_string_raises_jwt_error(self):
        with pytest.raises(JWTError):
            verify_access_token("not.a.valid.jwt")

    def test_different_users_produce_different_tokens(self):
        t1 = create_access_token(1, "a@b.com")
        t2 = create_access_token(2, "b@b.com")
        assert t1 != t2


# ---------------------------------------------------------------------------
# Secure random token generation
# ---------------------------------------------------------------------------

class TestSecureTokenGeneration:
    def test_returns_string(self):
        assert isinstance(generate_secure_token(), str)

    def test_tokens_are_unique(self):
        assert generate_secure_token() != generate_secure_token()

    def test_longer_bytes_produces_longer_token(self):
        assert len(generate_secure_token(64)) > len(generate_secure_token(8))
