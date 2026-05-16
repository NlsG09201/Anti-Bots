import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


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
