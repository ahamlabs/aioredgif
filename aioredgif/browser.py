"""Playwright fallback: the scripted version of DevTools' Network tab.

Used only when the API route fails, or when the caller asks for it. It opens
the page in headless Chromium, listens to network responses and keeps:

* ``*.redgifs.com/*.mp4`` requests, which are the direct video URLs;
* the ``api.redgifs.com/v2/gifs/<id>`` JSON, the same data the API client reads.

On creator pages it scrolls to load more tiles and collects the
``a.clickArea[href^="/watch/"]`` links.

Playwright is optional: install it with ``pip install aioredgif[browser]`` and
``playwright install chromium``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from typing import Any

from aioredgif.config import Settings
from aioredgif.parsing import ids_from_creator_html

log = logging.getLogger("aioredgif.browser")

MP4_RE = re.compile(r"https://[^/]*redgifs\.com/[^?#]+\.mp4")
# Trackers and ads are blocked: pages load faster and send less traffic.
BLOCKED = re.compile(r"(google-analytics|googletagmanager|amplitude|cookieyes|rgcams|servefilesonly|streamate)")


class BrowserResolver:
    """Resolves pages with a real (headless) browser.

    The browser starts on first use and is shared; at most two pages are open
    at a time.

    Args:
        settings: Server settings (user agent, headless flag, timeouts).
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._playwright: Any = None
        self._browser: Any = None
        self._lock = asyncio.Lock()
        self._slots = asyncio.Semaphore(2)

    async def _ensure_browser(self) -> None:
        async with self._lock:
            if self._browser:
                return
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.settings.browser_headless)

    async def close(self) -> None:
        """Shut the browser down, if it was started."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _new_context(self) -> Any:
        await self._ensure_browser()
        context = await self._browser.new_context(
            user_agent=self.settings.user_agent, viewport={"width": 1280, "height": 900}
        )
        await context.route(BLOCKED, lambda route: route.abort())
        return context

    async def watch(self, gif_id: str) -> dict:
        """Open ``/watch/<id>``, press play if needed and capture the media URLs.

        Args:
            gif_id: The post id.

        Returns:
            ``id``, ``hd``, ``sd``, ``poster``, ``captured`` (every .mp4 URL
            seen) and ``api`` (the post's JSON, if the page fetched it).
        """
        async with self._slots:
            context = await self._new_context()
            page = await context.new_page()
            mp4s: list[str] = []
            api_json: dict = {}

            async def on_response(response: Any) -> None:
                url = response.url
                if MP4_RE.match(url) and url not in mp4s:
                    mp4s.append(url)
                elif f"/v2/gifs/{gif_id}" in url and response.ok:
                    with contextlib.suppress(Exception):
                        api_json.update(await response.json())

            page.on("response", on_response)
            try:
                await page.goto(
                    f"{self.settings.site_base}/watch/{gif_id}",
                    wait_until="domcontentloaded",
                    timeout=self.settings.browser_timeout_ms,
                )
                await _dismiss_overlays(page)
                player = page.locator(f'[data-feed-item-id="{gif_id}"] .Player').first
                with contextlib.suppress(Exception):
                    await player.wait_for(timeout=8000)
                for _ in range(3):  # if it does not autoplay, click play like a person would
                    if mp4s:
                        break
                    playing = await page.evaluate("() => [...document.querySelectorAll('video')].some(v => !v.paused)")
                    if not playing and await player.count():
                        await player.click(timeout=3000)
                    await page.wait_for_timeout(1500)

                gif = api_json.get("gif") or {}
                urls = gif.get("urls") or {}
                poster = await page.get_attribute(f'[data-feed-item-id="{gif_id}"] img.Player-Poster', "src")
                return {
                    "id": gif_id,
                    "hd": urls.get("hd") or next((url for url in mp4s if "-mobile" not in url), None),
                    "sd": urls.get("sd") or next((url for url in mp4s if "-mobile" in url), None),
                    "poster": urls.get("poster") or poster,
                    "captured": mp4s,
                    "api": gif or None,
                }
            finally:
                await context.close()

    async def creator_ids(self, username: str, max_items: int = 200) -> list[str]:
        """Scroll a creator page and collect every ``/watch/<id>`` tile.

        Args:
            username: The creator handle.
            max_items: Stop after this many ids.

        Returns:
            Post ids in page order.
        """
        async with self._slots:
            context = await self._new_context()
            page = await context.new_page()
            try:
                await page.goto(
                    f"{self.settings.site_base}/users/{username}",
                    wait_until="domcontentloaded",
                    timeout=self.settings.browser_timeout_ms,
                )
                await _dismiss_overlays(page)
                ids: list[str] = []
                rounds_without_new = 0
                while len(ids) < max_items and rounds_without_new < 3:
                    found = [gif_id for gif_id in ids_from_creator_html(await page.content()) if gif_id not in ids]
                    ids += found
                    rounds_without_new = 0 if found else rounds_without_new + 1
                    await page.mouse.wheel(0, 4000)
                    await page.wait_for_timeout(1200)
                return ids[:max_items]
            finally:
                await context.close()


async def _dismiss_overlays(page: Any) -> None:
    """Choose "necessary cookies only" and confirm the age gate, when shown."""
    for selector in ("button.cky-btn-reject", "text=/I am 18|I'm over 18|Enter/i"):
        with contextlib.suppress(Exception):
            button = page.locator(selector).first
            if await button.is_visible(timeout=1500):
                await button.click(timeout=2000)
