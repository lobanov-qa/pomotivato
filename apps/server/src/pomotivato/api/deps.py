"""Request-scoped dependencies: one database transaction per request."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.clock import Clock


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a session whose transaction commits when the response leaves."""
    async with request.app.state.db.new_session() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session)]


def get_clock(request: Request) -> Clock:
    """Injectable server clock (tests swap app.state.clock for FakeClock)."""
    clock: Clock = request.app.state.clock
    return clock


ClockDep = Annotated[Clock, Depends(get_clock)]
