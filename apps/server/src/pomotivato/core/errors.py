"""Domain error types of the pure core (spec 01 §7).

Kept in one module so both models and validation can raise them without
import cycles. Each class maps to a spec rule so UI layers can branch on
error kind instead of parsing messages.
"""

from __future__ import annotations


class ValidationError(Exception):
    """Base for any spec-01 §7 violation, including deserialization."""


class TaskValidationError(ValidationError):
    """Task card rules: V1 title, V2 enum, V3 estimate_blocks."""


class RecurrenceValidationError(ValidationError):
    """V11 recurrence parameters."""


class ReviewValidationError(ValidationError):
    """V4 review score 1..5."""


class SettingsValidationError(ValidationError):
    """V5 session settings ranges."""


class DayPlanValidationError(ValidationError):
    """V9/V10 day plan slots and chunk bounds."""


class StatusTransitionError(ValidationError):
    """V7 kanban status machine."""


class ScienceFieldRequiredError(ValidationError):
    """V8 when_then required when settings demand science fields."""
