import pytest
from httpx import AsyncClient
from fastapi import status

from app.config import settings

@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    """
    Test the health check endpoint.
    """
    response = await async_client.get(f"{settings.API_V1_STR}/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "environment" in data
