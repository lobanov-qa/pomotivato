"""Shared fixtures for the Python test harness."""

import pytest
from fastapi.testclient import TestClient
from pomotivato.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """In-process HTTP client bound to the app, no real socket."""
    return TestClient(app)
