"""Async client for the RedGIFs v2 API, the same API the website uses.

On a watch page the ``<video>`` element only holds a ``blob:`` URL. The real
``.mp4`` address arrives in the JSON from ``/v2/gifs/<id>``, which is what this
client reads.

The client stays welcome by behaving well rather than by hiding: one real
temporary token, a fixed User-Agent, throttled and capped concurrency, and
backing off on 429/5xx with ``Retry-After`` respected. There is no fingerprint
spoofing, proxy rotation or token farming.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager

import httpx

from aioredgif.config import Settings
from aioredgif.models import Gif, Page

log = logging.getLogger("aioredgif.client")

TOKEN_LIFETIME = 20 * 3600  # tokens last about a day; refresh well before that
PAGE_SIZE = 80


class RedGifsError(Exception):
    """An upstream request failed.

    Attributes:
        status: The HTTP status, or 0 for network errors.
    """

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status


class Throttle:
    """Caps concurrent requests and spaces out their start times.

    Use it as ``async with throttle:`` around any upstream request. After a 429,
    :meth:`penalize` pushes every later request back.
    """

    def __init__(self, concurrency: int, min_interval: float) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._lock = asyncio.Lock()
        self._interval = min_interval
        self._next_start = 0.0

    async def __aenter__(self) -> None:
        await self._semaphore.acquire()
        async with self._lock:
            now = time.monotonic()
            wait = self._next_start - now
            self._next_start = max(now, self._next_start) + self._interval
        if wait > 0:
            await asyncio.sleep(wait)

    async def __aexit__(self, *exc_info: object) -> None:
        self._semaphore.release()

    def penalize(self, seconds: float) -> None:
        """Delay every request that has not started yet by ``seconds``."""
        self._next_start = max(self._next_start, time.monotonic() + seconds)


def backoff(attempt: int) -> float:
    """Exponential backoff with jitter, capped at a minute.

    Args:
        attempt: Zero-based retry number.

    Returns:
        Seconds to wait.
    """
    return min(60.0, 2**attempt) + random.uniform(0, 1)


class RedGifsClient:
    """Talks to RedGIFs on behalf of every user of the server.

    Args:
        settings: Server settings.
        transport: Optional httpx transport, used by the tests to fake RedGIFs.
    """

    #: Equivalent sort words to try when RedGIFs refuses the one asked for.
    ORDER_ALIASES = {
        "new": ["new", "latest"],
        "latest": ["latest", "new"],
        "top": ["top", "best"],
        "best": ["best", "top"],
        "trending": ["trending", "hot"],
        "hot": ["hot", "trending"],
        "oldest": ["oldest"],
    }

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self._http = httpx.AsyncClient(
            base_url=settings.api_base,
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "application/json",
                "Origin": settings.site_base,
                "Referer": settings.site_base + "/",
            },
            timeout=settings.request_timeout,
            follow_redirects=True,
            transport=transport,
        )
        self.throttle = Throttle(settings.upstream_concurrency, settings.upstream_min_interval)
        self._token: str | None = None
        self._token_expires = 0.0
        self._token_lock = asyncio.Lock()
        self._working_order: dict[tuple[str, str], str | None] = {}

    async def aclose(self) -> None:
        """Close the underlying HTTP connections."""
        await self._http.aclose()

    # ------------------------------------------------------------------ auth

    async def _token_for_request(self, force: bool = False) -> str:
        async with self._token_lock:
            if self._token and not force and time.time() < self._token_expires:
                return self._token
            async with self.throttle:
                response = await self._http.get("/v2/auth/temporary")
            if response.status_code != 200:
                raise RedGifsError(response.status_code, "could not obtain a temporary token")
            self._token = response.json()["token"]
            self._token_expires = time.time() + TOKEN_LIFETIME
            log.info("obtained a new temporary token")
            return self._token

    # ---------------------------------------------------------- core request

    async def get_json(self, path: str, params: dict | None = None) -> dict:
        """GET an API path with auth, throttling and retries.

        Args:
            path: API path such as ``"/v2/gifs/abc"``.
            params: Query parameters.

        Returns:
            The decoded JSON body.

        Raises:
            RedGifsError: When RedGIFs refuses the request or keeps failing.
        """
        refreshed = False
        response = None
        for attempt in range(self.settings.max_retries + 1):
            token = await self._token_for_request()
            try:
                async with self.throttle:
                    response = await self._http.get(path, params=params, headers={"Authorization": f"Bearer {token}"})
            except httpx.TransportError as exc:
                if attempt == self.settings.max_retries:
                    raise RedGifsError(0, f"network error: {exc}") from exc
                await asyncio.sleep(backoff(attempt))
                continue

            if response.status_code == 200:
                return response.json()
            if response.status_code == 401 and not refreshed:
                refreshed = True
                await self._token_for_request(force=True)
                continue
            if response.status_code == 404:
                raise RedGifsError(404, "not found")
            if response.status_code == 429 or response.status_code >= 500:
                wait = _retry_after(response) or backoff(attempt)
                if response.status_code == 429:
                    self.throttle.penalize(wait)
                log.warning("upstream %s on %s, waiting %.1fs", response.status_code, path, wait)
                if attempt == self.settings.max_retries:
                    break
                await asyncio.sleep(wait)
                continue
            raise RedGifsError(response.status_code, _error_text(response))
        raise RedGifsError(response.status_code if response else 0, "gave up after retries")

    async def _get_sorted(self, feed: str, path: str, params: dict, order: str) -> dict:
        """GET a feed, falling back when RedGIFs refuses the sort order.

        RedGIFs feeds do not all accept the same sort words, and the error can
        even reject a word it lists as allowed. On a "bad sorting order" 400
        this tries the nearest equivalent, then no order (the server default),
        then whatever the error lists, and remembers what worked per feed.
        """
        known = self._working_order.get((feed, order), ...)
        if known is not ...:
            return await self.get_json(path, params if known is None else {**params, "order": known})

        candidates: list[str | None] = [*self.ORDER_ALIASES.get(order, [order]), None]
        tried: list[str | None] = []
        first_error: RedGifsError | None = None
        index = 0
        while index < len(candidates):
            candidate = candidates[index]
            index += 1
            if candidate in tried:
                continue
            tried.append(candidate)
            try:
                data = await self.get_json(path, params if candidate is None else {**params, "order": candidate})
            except RedGifsError as exc:
                if exc.status != 400 or "sort" not in str(exc).lower():
                    raise
                first_error = first_error or exc
                allowed = re.search(r"one of:?\s*([A-Za-z_, ]+)", str(exc))
                if allowed:
                    listed = [word.strip().lower() for word in allowed.group(1).split(",") if word.strip()]
                    # "oldest" is valid but rarely what anyone wants, so it goes last.
                    candidates += [word for word in listed if word != "oldest"] + [w for w in listed if w == "oldest"]
                continue
            self._working_order[(feed, order)] = candidate
            if candidate != order:
                used = "the server default" if candidate is None else repr(candidate)
                log.warning("%s: RedGIFs refused order=%r, using %s instead", feed, order, used)
            return data
        raise RedGifsError(400, f"RedGIFs refused every sort order for this feed (tried {tried}): {first_error}")

    # ------------------------------------------------------------ endpoints

    async def gif(self, gif_id: str) -> Gif:
        """Fetch one post by id."""
        data = await self.get_json(f"/v2/gifs/{gif_id.lower()}", {"views": "yes", "users": "yes"})
        return Gif.from_api(data["gif"])

    async def gifs_by_ids(self, ids: list[str]) -> list[Gif]:
        """Fetch many posts by id, 100 per upstream call."""
        found: list[Gif] = []
        for start in range(0, len(ids), 100):
            chunk = ",".join(gif_id.lower() for gif_id in ids[start : start + 100])
            data = await self.get_json("/v2/gifs", {"ids": chunk})
            found += [Gif.from_api(item) for item in data.get("gifs", [])]
        return found

    async def user_gifs(self, username: str, page: int = 1, count: int = PAGE_SIZE, order: str = "new") -> Page:
        """One page of a creator's posts."""
        data = await self._get_sorted(
            "user", f"/v2/users/{username.lower()}/search", {"count": count, "page": page}, order
        )
        return _to_page(data, page)

    async def user(self, username: str) -> dict:
        """A creator's public profile."""
        return await self.get_json(f"/v1/users/{username.lower()}")

    async def search(self, tags: list[str], page: int = 1, count: int = PAGE_SIZE, order: str = "trending") -> Page:
        """One page of posts carrying all of ``tags``."""
        data = await self._get_sorted(
            "search", "/v2/gifs/search", {"search_text": ",".join(tags), "count": count, "page": page}, order
        )
        return _to_page(data, page)

    async def niche_gifs(self, niche: str, page: int = 1, count: int = PAGE_SIZE, order: str = "trending") -> Page:
        """One page of a niche's feed."""
        data = await self._get_sorted(
            "niche", f"/v2/niches/{niche.lower()}/gifs", {"count": count, "page": page}, order
        )
        return _to_page(data, page)

    async def niche(self, niche: str) -> dict:
        """A niche's name, description and counts."""
        data = await self.get_json(f"/v2/niches/{niche.lower()}")
        return data.get("niche", data)

    async def iter_user(self, username: str, limit: int, order: str = "new") -> AsyncIterator[Gif]:
        """Yield up to ``limit`` posts from a creator, page by page."""
        async for gif in _paginate(lambda page: self.user_gifs(username, page, PAGE_SIZE, order), limit):
            yield gif

    async def iter_niche(self, niche: str, limit: int, order: str = "trending") -> AsyncIterator[Gif]:
        """Yield up to ``limit`` posts from a niche."""
        async for gif in _paginate(lambda page: self.niche_gifs(niche, page, PAGE_SIZE, order), limit):
            yield gif

    async def iter_search(self, tags: list[str], limit: int, order: str = "trending") -> AsyncIterator[Gif]:
        """Yield up to ``limit`` posts from a tag search."""
        async for gif in _paginate(lambda page: self.search(tags, page, PAGE_SIZE, order), limit):
            yield gif

    # ----------------------------------------------------------------- media

    def stream(self, url: str, headers: dict | None = None) -> AbstractAsyncContextManager[httpx.Response]:
        """Stream a media file with the site's User-Agent and Referer.

        Use as ``async with client.stream(url) as response:``.
        """
        return self._http.stream("GET", url, headers={"Accept": "*/*", **(headers or {})})

    async def fetch_image(self, url: str) -> httpx.Response:
        """Fetch a thumbnail or poster image (throttled)."""
        async with self.throttle:
            return await self._http.get(url, headers={"Accept": "image/*"})


async def _paginate(fetch: Callable[[int], Awaitable[Page]], limit: int) -> AsyncIterator[Gif]:
    taken, page = 0, 1
    while taken < limit:
        result = await fetch(page)
        if not result.items:
            return
        for gif in result.items:
            yield gif
            taken += 1
            if taken >= limit:
                return
        if page >= result.pages:
            return
        page += 1


def _to_page(data: dict, page: int) -> Page:
    return Page(
        items=[Gif.from_api(item) for item in data.get("gifs", [])],
        page=data.get("page", page),
        pages=data.get("pages", 1),
        total=data.get("total", 0),
        users=[user for user in data.get("users") or [] if isinstance(user, dict)],
    )


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
        return body.get("error", {}).get("message") or str(body)
    except ValueError:
        return response.text[:200]
