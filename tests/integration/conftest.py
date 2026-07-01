"""
Integration test conftest.

Creates a FastAPI TestClient with all external dependencies overridden:
  - get_current_verified_user -> mock verified user (no JWT/DB needed)
  - every service dependency    -> MagicMock instance
  - get_db                      -> MagicMock session

Each test gets fresh mock access via module-level MOCKS dict.
"""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from main import app
from app.auth_module.models.user import User
from app.core.security import create_access_token

# Shared mock storage so individual tests can configure return values
MOCKS: dict = {}


@pytest.fixture(scope="module")
def verified_user():
    user = MagicMock(spec=User)
    user.id = 1
    user.email = "integration@fitmind.test"
    user.name = "Integration Tester"
    user.is_verified = True
    user.password = "$2b$12$fakehash"
    return user


@pytest.fixture(scope="module")
def client(verified_user):
    """Module-scoped TestClient; dependency overrides are set once."""
    from app.auth_module.core.dependencies import (
        get_current_verified_user,
        get_auth_service,
        get_otp_service,
        get_auth_email_service,
    )
    from app.core.dependencies import get_current_user, get_current_verified_user as core_verified
    from app.profile_module.core.dependencies import get_profile_service
    from app.planning_module.core.dependencies import get_plan_generation_service
    from app.tracking_module.core.dependencies import (
        get_tracking_service,
        get_meal_scanner_service_dep,
        get_voice_transcriber_service_dep,
    )
    from app.recommendation_system.core.dependencies import get_recommendation_service
    from app.db.database import get_db

    mock_db = MagicMock()

    MOCKS["auth"] = MagicMock()
    MOCKS["otp"] = MagicMock()
    MOCKS["email"] = MagicMock()
    MOCKS["profile"] = MagicMock()
    MOCKS["plan"] = MagicMock()
    MOCKS["tracking"] = MagicMock()
    MOCKS["recommendation"] = MagicMock()

    app.dependency_overrides = {
        get_db: lambda: mock_db,
        get_current_user: lambda: verified_user,
        get_current_verified_user: lambda: verified_user,
        core_verified: lambda: verified_user,
        get_auth_service: lambda: MOCKS["auth"],
        get_otp_service: lambda: MOCKS["otp"],
        get_auth_email_service: lambda: MOCKS["email"],
        get_profile_service: lambda: MOCKS["profile"],
        get_plan_generation_service: lambda: MOCKS["plan"],
        get_tracking_service: lambda: MOCKS["tracking"],
        get_meal_scanner_service_dep: lambda: MagicMock(),
        get_voice_transcriber_service_dep: lambda: MagicMock(),
        get_recommendation_service: lambda: MOCKS["recommendation"],
    }

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset all mocks before each test to avoid state bleed."""
    for m in MOCKS.values():
        m.reset_mock()


# Convenience fixtures so tests don't touch MOCKS directly
@pytest.fixture
def mock_auth(reset_mocks):
    return MOCKS["auth"]

@pytest.fixture
def mock_profile(reset_mocks):
    return MOCKS["profile"]

@pytest.fixture
def mock_plan(reset_mocks):
    return MOCKS["plan"]

@pytest.fixture
def mock_tracking(reset_mocks):
    return MOCKS["tracking"]

@pytest.fixture
def mock_recommendation(reset_mocks):
    return MOCKS["recommendation"]

@pytest.fixture
def token(verified_user):
    return create_access_token(verified_user.id, verified_user.email)

@pytest.fixture
def headers(token):
    return {"Authorization": f"Bearer {token}"}
