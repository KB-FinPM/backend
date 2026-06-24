def test_cors_allows_localhost_dev_origin(client) -> None:
    response = client.get(
        "/api/health",
        headers={"Origin": "http://127.0.0.1:5173"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_cors_allows_any_local_dev_port(client) -> None:
    response = client.get(
        "/api/health",
        headers={"Origin": "http://localhost:4321"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:4321"
