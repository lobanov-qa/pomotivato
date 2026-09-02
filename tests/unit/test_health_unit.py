"""Unit tests for pure functions callable without the HTTP layer."""

import pytest
from pomotivato.main import health


@pytest.mark.unit
def test_health_reports_ok_when_called_directly():
    assert health() == {"status": "ok"}
