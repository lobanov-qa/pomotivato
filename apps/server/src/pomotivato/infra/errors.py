"""Infrastructure-level errors that are not domain validation (spec 02 §5).

Core raises its own ValidationError family; these carry HTTP semantics the
API layer maps to 404/409 without importing fastapi into the services.
"""

from __future__ import annotations


class NotFoundError(Exception):
    """Requested entity does not exist (API maps to 404)."""


class ConflictError(Exception):
    """Request conflicts with stored state or policy (API maps to 409)."""
