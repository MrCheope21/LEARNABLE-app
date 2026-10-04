import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from app.api.documents import get_max_upload_bytes
from app.api.errors import register_exception_handlers
from app.api.headers import SecurityHeadersMiddleware
from app.api.limits import MULTIPART_OVERHEAD_BYTES, BodySizeLimitMiddleware
from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_session_factory
from app.services.recovery import recover_stale_jobs
from app.web import install_web_app

logger = logging.getLogger(__name__)


def sweep_interrupted_jobs(session_factory: sessionmaker[Session]) -> None:
    """One recovery pass. Never raises: recovery must not stop the server or its loop."""
    try:
        with session_factory() as db:
            recover_stale_jobs(db)
    except Exception:
        logger.exception("Recovery of interrupted jobs failed")


async def _recovery_loop(interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        await asyncio.to_thread(sweep_interrupted_jobs, _session_factory())


def _session_factory() -> sessionmaker[Session]:
    factory: sessionmaker[Session] = app.dependency_overrides.get(
        get_session_factory, get_session_factory
    )()
    return factory


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Validate configuration at startup so a missing/weak AUTH_SECRET stops the server
    # immediately, instead of surfacing as a 500 on the first authenticated request.
    settings = get_settings()
    configure_logging(settings.log_level)
    interval = settings.job_recovery_interval_seconds
    if not interval:
        yield
        return
    # Jobs run in-process: any left PROCESSING/GENERATING by a previous process are lost.
    await asyncio.to_thread(sweep_interrupted_jobs, _session_factory())
    loop = asyncio.create_task(_recovery_loop(interval))
    try:
        yield
    finally:
        loop.cancel()
        with suppress(asyncio.CancelledError):
            await loop


app = FastAPI(title="Adaptive AI Learning Platform API", lifespan=lifespan)
register_exception_handlers(app)
app.add_middleware(
    BodySizeLimitMiddleware,
    limit_bytes=lambda: get_max_upload_bytes() + MULTIPART_OVERHEAD_BYTES,
)
# Added last, so it runs first and also covers error responses from the other middleware.
app.add_middleware(SecurityHeadersMiddleware)
app.include_router(api_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Last: only paths no route matched reach it (and only when WEB_DIST_DIR is set).
install_web_app(app)
