"""API-level floor of the test pyramid: liveness and error contract."""

import pytest


@pytest.mark.smoke
@pytest.mark.api
def test_health_endpoint_returns_ok_when_server_runs(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.api
@pytest.mark.parametrize("path", ["/nope", "/api/sessions", "/healthz"])
def test_unknown_route_returns_404_when_path_not_registered(client, path):
    response = client.get(path)

    assert response.status_code == 404
