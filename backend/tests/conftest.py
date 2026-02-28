"""
Pytest fixtures.

Requirements:
  - docker-compose up -d postgres   (or equivalent Postgres running on localhost:5432)
  - DATABASE_URL env var pointing to the test database
  - uv run alembic upgrade head     (run once before tests)

Run:
  uv run pytest
"""
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Ensure test env picks up .env or env vars set externally
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/bible_therapist")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-not-for-production")
os.environ.setdefault("ENVIRONMENT", "development")

from app.main import app  # noqa: E402 — import after env setup


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """Exchange a dev id_token for a Bearer JWT."""
    dev_id = f"test-user-{uuid.uuid4()}"
    resp = await client.post("/v1/auth/token", json={"grant_type": "apple_id_token", "id_token": dev_id})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
