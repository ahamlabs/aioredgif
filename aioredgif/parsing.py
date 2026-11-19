"""Turn RedGIFs links and saved page HTML into post ids.

This mirrors finding things by hand in the browser: on a creator page every
tile is an ``<a class="clickArea" href="/watch/<id>">``, and on a watch page
every feed item carries ``data-feed-item-id="<id>"``. Ids are all that is
needed; the media URLs come from the API.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

ID_RE = re.compile(r"^[a-z]+$")  # post ids are lowercase words run together

_PATH_PATTERNS = [
    ("watch", re.compile(r"^/(?:watch|ifr|i)/([A-Za-z]+)")),
    ("creator", re.compile(r"^/users/([^/?#]+)")),
    ("tag", re.compile(r"^/gifs/([^/?#]+)")),
    ("niche", re.compile(r"^/niches/([^/?#]+)")),
]


def classify_url(url: str) -> tuple[str, str | None]:
    """Work out what a RedGIFs link points at.

    Args:
        url: Any RedGIFs link, with or without ``https://``. Media links such as
            ``media.redgifs.com/<Name>-mobile.jpg`` count as watch links.

    Returns:
        ``(kind, value)`` where kind is ``"watch"``, ``"creator"``, ``"tag"``,
        ``"niche"`` or ``"unknown"`` (value is then None). Watch ids and niche
        slugs are lowercased; creator handles and tags keep their case.

    Examples:
        >>> classify_url("https://www.redgifs.com/users/paul57ak57")
        ('creator', 'paul57ak57')
        >>> classify_url("redgifs.com/niches/lost-bet-captions")
        ('niche', 'lost-bet-captions')
    """
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.hostname or "").lower()

    if host.startswith(("media.", "thumbs")):
        stem = parsed.path.rsplit("/", 1)[-1].split(".")[0].split("-")[0]
        return ("watch", stem.lower()) if stem else ("unknown", None)
    if "redgifs.com" not in host:
        return "unknown", None

    if parsed.path.startswith("/browse"):
        tags = parse_qs(parsed.query).get("tags")
        return ("tag", tags[0]) if tags else ("unknown", None)
    for kind, pattern in _PATH_PATTERNS:
        match = pattern.match(parsed.path)
        if match:
            value = unquote(match.group(1))
            return kind, value.lower() if kind in ("watch", "niche") else value
    return "unknown", None


def ids_from_feed_html(html: str) -> list[str]:
    """Post ids from ``data-feed-item-id`` attributes, skipping ad and promo modules."""
    soup = BeautifulSoup(html, "html.parser")
    ids: list[str] = []
    for element in soup.select("[data-feed-item-id]"):
        if element.has_attr("data-feed-module-type"):
            continue  # OnlyFans, live-cam and "trending niches" blocks
        gif_id = element["data-feed-item-id"].lower()
        if ID_RE.match(gif_id) and gif_id not in ids:
            ids.append(gif_id)
    return ids


def ids_from_creator_html(html: str) -> list[str]:
    """Post ids of every tile on a creator page, in page order."""
    soup = BeautifulSoup(html, "html.parser")
    ids: list[str] = []
    for link in soup.select('a.clickArea[href^="/watch/"]'):
        gif_id = link["href"].split("/watch/", 1)[1].split("?")[0].lower()
        if ID_RE.match(gif_id) and gif_id not in ids:
            ids.append(gif_id)
    return ids or ids_from_feed_html(html)


def active_watch_id(html: str) -> str | None:
    """Id of the post a saved watch page was showing."""
    soup = BeautifulSoup(html, "html.parser")
    element = soup.select_one(".GifPreview_isActive[data-feed-item-id]")
    return element["data-feed-item-id"].lower() if element else None


def creator_from_html(html: str) -> str | None:
    """The creator's handle (from ``/users/<name>`` links), not the display name."""
    soup = BeautifulSoup(html, "html.parser")
    link = soup.select_one('a[href^="/users/"]')
    if link:
        return link["href"].split("/users/", 1)[1].strip("/")
    tile = soup.select_one("a.clickArea[aria-label]")  # creator pages: "... uploaded by <user> on ..."
    if tile:
        match = re.search(r"uploaded by (\S+) on", tile["aria-label"])
        if match:
            return match.group(1)
    return None


def posters_from_html(html: str) -> dict[str, str]:
    """Map post id to poster URL, from ``<img src=".../<Name>-mobile.jpg">`` tags."""
    soup = BeautifulSoup(html, "html.parser")
    posters: dict[str, str] = {}
    for image in soup.select('img[src*="media.redgifs.com"]'):
        _, gif_id = classify_url(image["src"])
        if gif_id and gif_id not in posters:
            posters[gif_id] = image["src"]
    return posters
