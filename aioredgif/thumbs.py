"""Thumbnail cache: images fetched once from RedGIFs and kept in ``.thumbs``."""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse

from aioredgif.client import RedGifsClient

IMAGE_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}


class ThumbnailError(Exception):
    """A thumbnail could not be served.

    Attributes:
        status: The HTTP status the API should answer with.
    """

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class ThumbCache:
    """Fetches thumbnails through the server and caches them on disk.

    The page never hotlinks RedGIFs: it asks this server, which fetches with the
    site's User-Agent and Referer once and keeps the file.

    Args:
        root: The download directory; the cache lives in ``<root>/.thumbs``.
        client: The RedGIFs client.
    """

    def __init__(self, root: Path, client: RedGifsClient) -> None:
        self.dir = root / ".thumbs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.client = client
        self._slots = asyncio.Semaphore(4)

    def cached(self, gif_id: str) -> Path | None:
        """The cached thumbnail for ``gif_id``, if there is one."""
        return next((path for path in self.dir.glob(f"{gif_id}.*") if path.suffix != ".part"), None)

    async def get(self, gif_id: str, url: str | None) -> Path:
        """Return a cached thumbnail, fetching it from ``url`` first if needed.

        Args:
            gif_id: The post id (the cache key).
            url: Where to fetch it from; must be a redgifs.com address.

        Returns:
            The path of the cached image.

        Raises:
            ThumbnailError: 404 when there is nothing to fetch, 400 for a foreign
                host, 502 when RedGIFs does not return an image.
        """
        hit = self.cached(gif_id)
        if hit:
            return hit
        if not url:
            raise ThumbnailError(404, "no thumbnail")
        host = (urlparse(url).hostname or "").lower()
        if not (host == "redgifs.com" or host.endswith(".redgifs.com")):
            raise ThumbnailError(400, "unexpected thumbnail host")
        ext = url.split("?", 1)[0].rsplit(".", 1)[-1].lower()
        ext = ext if ext in IMAGE_TYPES else "jpg"
        async with self._slots:
            try:
                response = await self.client.fetch_image(url)
            except Exception as exc:  # noqa: BLE001 - reported to the caller as a 502
                raise ThumbnailError(502, f"thumbnail fetch failed: {exc}") from exc
        if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
            raise ThumbnailError(502, f"thumbnail fetch failed: {response.status_code}")
        target = self.dir / f"{gif_id}.{ext}"
        temp = target.with_suffix(".part")
        temp.write_bytes(response.content)
        temp.replace(target)
        return target


def media_type(path: Path) -> str:
    """Content type for an image path."""
    return IMAGE_TYPES.get(path.suffix.lstrip(".").lower(), "image/jpeg")
