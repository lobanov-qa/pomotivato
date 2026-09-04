"""Error handlers: domain/infra exceptions -> stable HTTP JSON (spec 02 §5).

Mapping by exception family, not by message text, so clients can branch on
`detail.code`. Core raises validation errors; services translate conflicts;
FastAPI RequestValidationError means the DTO itself was malformed.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pomotivato.core.errors import (
    InvalidReviewError,
    InvalidTransitionError,
    StatusTransitionError,
    ValidationError,
)
from pomotivato.infra.errors import ConflictError, NotFoundError


def register_error_handlers(app: FastAPI) -> None:
    """Attach all exception->response translations to the app."""

    @app.exception_handler(NotFoundError)
    async def not_found(_request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": {"code": "not_found", "message": str(exc)}},
        )

    @app.exception_handler(ConflictError)
    async def conflict(_request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": {"code": "conflict", "message": str(exc)}},
        )

    # Starlette accepts one class per handler call, not a tuple.
    for conflict_exc in (StatusTransitionError, InvalidTransitionError, InvalidReviewError):

        @app.exception_handler(conflict_exc)
        async def domain_conflict(_request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"detail": {"code": "conflict", "message": str(exc)}},
            )

    @app.exception_handler(ValidationError)
    async def domain_invalid(_request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": {"code": "invalid", "message": str(exc)}},
        )

    @app.exception_handler(RequestValidationError)
    async def request_invalid(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": {"code": "invalid", "message": str(exc)}},
        )
