"""The FastAPI application.

``app`` is ready for ``uvicorn aioredgif.app:app``. Use :func:`create_app` to
build one with your own settings, or with a fake RedGIFs for tests.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from aioredgif import __version__
from aioredgif.api import brand, faves, gifs, jobs, library, profile
from aioredgif.browser import BrowserResolver
from aioredgif.config import Settings, get_settings
from aioredgif.faves import FaveStore
from aioredgif.ratelimit import TokenBucket
from aioredgif.rewards import ProfileStore
from aioredgif.services import Services, open_services

STATIC_DIR = Path(__file__).resolve().parent / "static"
log = logging.getLogger("aioredgif")


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    """Build an aioredgif application.

    Args:
        settings: Settings to use; read from the environment when omitted.
        transport: Optional httpx transport for RedGIFs traffic (tests use a mock).

    Returns:
        The app. Its services are created on startup and stored on ``app.state``:
        ``settings``, ``client``, ``library``, ``jobs``, ``thumbs``, ``faves``,
        ``profiles``, ``rate_buckets`` and ``browser``.
    """
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with open_services(settings, transport) as services, _serve(app, services):
            yield

    @asynccontextmanager
    async def _serve(app: FastAPI, services: Services) -> AsyncIterator[None]:
        state = app.state
        state.settings = settings
        state.client = services.client
        state.library = services.library
        state.jobs = services.jobs
        state.thumbs = services.thumbs
        state.faves = FaveStore(settings.download_dir)
        state.profiles = ProfileStore(settings.download_dir)
        state.rate_buckets = TokenBucket()
        state.browser = BrowserResolver(settings) if settings.browser_enabled else None
        log.info("library: %d files in %s", len(state.library), settings.download_dir.resolve())
        if settings.auto_resume:
            resumed = state.jobs.resume_interrupted()
            if resumed:
                log.info("resuming %d interrupted pull(s): %s", len(resumed), resumed)
        try:
            yield
        finally:
            if state.browser:
                await state.browser.close()

    app = FastAPI(
        title="aioredgif",
        version=__version__,
        summary="Pull, keep, browse and play RedGIFs posts. Adults only.",
        description=(
            "An async RedGIFs downloader with a library, player and goon cave. "
            "See docs/API.md for a walkthrough with curl examples."
        ),
        lifespan=lifespan,
    )

    @app.get("/health", tags=["Site"])
    async def health() -> dict:
        """Liveness check."""
        return {"ok": True, "version": __version__}

    for module in (gifs, jobs, library, faves, profile, brand):
        app.include_router(module.router)

    # The web page. Mounted last so it never shadows an API route.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
