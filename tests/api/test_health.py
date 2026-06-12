# EN: Tests for health check API behavior.
# KO: Health Check API 동작을 검증하는 테스트입니다.

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "FINPM API is running",
    }
