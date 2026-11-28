import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from app.services.visitor_sessions import purge_expired_visitor_sessions

logger = logging.getLogger(__name__)
CLEANUP_INTERVAL_SECONDS = 300


async def _cleanup_expired_sessions() -> None:
    while True:
        try:
            await asyncio.to_thread(purge_expired_visitor_sessions)
        except SQLAlchemyError:
            logger.exception("Failed to purge expired visitor sessions.")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    cleanup_task = asyncio.create_task(_cleanup_expired_sessions())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
