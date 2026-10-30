import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_checks_database(client: AsyncClient):
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_validation_error_envelope_does_not_echo_submitted_secrets(client: AsyncClient):
    sentinel = "do-not-return-this-password"
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": sentinel},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "VALIDATION_ERROR"
    assert body["message"] == "Request validation failed"
    assert body["detail"]
    assert sentinel not in response.text
    assert all("input" not in item for item in body["detail"])


@pytest.mark.asyncio
async def test_http_error_envelope_keeps_detail_for_compatibility(client: AsyncClient):
    response = await client.get("/route-that-does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "error": "HTTP_ERROR",
        "message": "Not Found",
        "detail": "Not Found",
    }


@pytest.mark.asyncio
async def test_viewer_cannot_execute_moderation_playbook(client: AsyncClient):
    from uuid import uuid4

    from app.api.dependencies import get_current_user
    from app.infrastructure.database.models import User, UserRole
    from app.main import app

    viewer = User(
        id=uuid4(),
        tenant_id=uuid4(),
        email="viewer@test.com",
        username="viewer",
        hashed_password="unused-test-hash",
        role=UserRole.VIEWER,
    )

    async def get_viewer():
        return viewer

    app.app.dependency_overrides[get_current_user] = get_viewer
    response = await client.post(
        f"/api/v1/soc/playbooks/{uuid4()}/execute",
        params={"incident_id": str(uuid4())},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_api_cors_preflight_allows_configured_frontend(client: AsyncClient):
    from app.core.config import get_settings

    origin = get_settings().cors_origins_list[0]
    response = await client.options(
        "/api/v1/streams/00000000-0000-0000-0000-000000000000/viewers/load-full",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    register_data = {
        "email": "streamer@test.com",
        "username": "teststreamer",
        "password": "SecurePass123!",
        "tenant_name": "Test Channel",
    }
    response = await client.post("/api/v1/auth/register", json=register_data)
    assert response.status_code == 200
    tokens = response.json()
    assert "access_token" in tokens
    assert tokens.get("refresh_token", "") == ""

    login_response = await client.post("/api/v1/auth/login", json={
        "email": "streamer@test.com",
        "password": "SecurePass123!",
    })
    assert login_response.status_code == 200


@pytest.mark.asyncio
async def test_fingerprint_submission(client: AsyncClient):
    register_data = {
        "email": "fp@test.com",
        "username": "fpuser",
        "password": "SecurePass123!",
        "tenant_name": "FP Test",
    }
    await client.get("/api/v1/auth/csrf")
    reg = await client.post("/api/v1/auth/register", json=register_data)
    token = reg.json()["access_token"]

    fp_data = {
        "canvas_hash": "abc123",
        "webgl_hash": "def456",
        "screen_resolution": "1920x1080",
        "webdriver": False,
        "selenium": False,
    }
    response = await client.post(
        "/api/v1/detection/fingerprint",
        json=fp_data,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "hash" in data
    assert "risk_score" in data
