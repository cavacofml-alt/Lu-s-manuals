from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_health_reports_extensions(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["database"]["connected"] is True
    assert "pg_trgm" in body["database"]["extensions"]


def test_releases_is_empty_until_step_2(client: TestClient) -> None:
    assert client.get("/api/v1/releases").json() == []
