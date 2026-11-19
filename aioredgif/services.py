"""The services aioredgif runs on, shared by the web server and the command line."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx

from aioredgif.client import RedGifsClient
from aioredgif.config import Settings
from aioredgif.downloader import JobManager
from aioredgif.library import Library
from aioredgif.thumbs import ThumbCache


@dataclass
class Services:
    """Everything needed to look things up, pull and browse.

    Attributes:
        settings: The settings in use.
        client: RedGIFs API client.
        library: Index of downloaded files.
        jobs: Runs and remembers pulls.
        thumbs: Thumbnail cache.
    """

    settings: Settings
    client: RedGifsClient
    library: Library
    jobs: JobManager
    thumbs: ThumbCache


@asynccontextmanager
async def open_services(
    settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> AsyncIterator[Services]:
    """Start the services, and on exit save running pulls as interrupted and close connections.

    Args:
        settings: Settings to use.
        transport: Optional httpx transport for RedGIFs traffic (tests use a mock).

    Yields:
        The running services.
    """
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    client = RedGifsClient(settings, transport=transport)
    library = Library(settings.download_dir, settings.library_rescan_seconds)
    services = Services(
        settings=settings,
        client=client,
        library=library,
        jobs=JobManager(client, settings, library),
        thumbs=ThumbCache(settings.download_dir, client),
    )
    try:
        yield services
    finally:
        await services.jobs.shutdown()
        await client.aclose()
