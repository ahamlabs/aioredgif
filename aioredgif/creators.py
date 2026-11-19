"""Creator reports: a creator's profile, every post, and an analysis of them.

A report is one JSON document with a versioned schema (``"schema":
"aioredgif.creator/1"``), built from what RedGIFs exposes publicly. It can be
built online (from RedGIFs) or offline (from the library's sidecars). See
``docs/DATA.md`` for every field.

Typical use::

    async with open_services(settings) as services:
        report = await creator_report(services.client, "somecreator", library=services.library)
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from aioredgif import __version__
from aioredgif.client import RedGifsClient, RedGifsError
from aioredgif.library import Library
from aioredgif.metadata import SITE, compute_stats, gif_record
from aioredgif.models import FileResult, Gif

SCHEMA = "aioredgif.creator/1"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _pick(raw: dict, *keys: str) -> object:
    """First present, non-empty value among ``keys`` (RedGIFs field names vary)."""
    for key in keys:
        value = raw.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _iso(value: object) -> str | None:
    """A timestamp (seconds or ISO text) as ISO 8601 UTC, or None."""
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value, UTC).isoformat()
    if isinstance(value, str) and value:
        return value
    return None


def normalise_profile(raw: dict, username: str) -> dict:
    """A creator profile in stable field names, whatever RedGIFs called them.

    Args:
        raw: Profile object from RedGIFs (``/v1/users/<name>`` or the ``users``
            list sent with feeds). May be empty.
        username: The handle asked for, used when the profile lacks one.

    Returns:
        ``username, display_name, profile_url, profile_image, description,
        verified, followers, following, views, likes, total_posts,
        published_collections, joined, links`` and ``raw`` (the original).
    """
    handle = _pick(raw, "username", "userName", "name") or username
    links = _pick(raw, "links", "socialUrls", "social")
    return {
        "username": handle,
        "display_name": _pick(raw, "name", "displayName", "display_name"),
        "profile_url": f"{SITE}/users/{handle}",
        "profile_image": _pick(raw, "profileImageUrl", "profile_image", "profileImage", "avatar", "avatarUrl"),
        "description": _pick(raw, "description", "bio"),
        "verified": _pick(raw, "verified"),
        "followers": _pick(raw, "followers", "followerCount"),
        "following": _pick(raw, "following", "followingCount"),
        "views": _pick(raw, "views", "viewCount"),
        "likes": _pick(raw, "likes", "likeCount"),
        "total_posts": _pick(raw, "publishedGifs", "gifs", "gifCount"),
        "published_collections": _pick(raw, "publishedCollections"),
        "joined": _iso(_pick(raw, "creationtime", "createDate", "created", "createdAt")),
        "links": links,
        "raw": raw,
    }


def post_record(gif: Gif, library: Library | None, root: Path | None) -> dict:
    """One post as stored in reports: its sidecar record plus how to download it.

    The ``download`` block lists the direct media URLs and the aioredgif ways to
    fetch the post (API and command line). ``file`` is set when the post is
    already in the library.
    """
    path = library.get(gif.id) if library else None
    result = FileResult(id=gif.id, path=str(path), bytes=path.stat().st_size, skipped=True) if path else None
    record = gif_record(gif, result, root or Path("."))
    record.pop("status", None)
    record.pop("error", None)
    record["orientation"] = _orientation(gif.width, gif.height)
    record["download"] = {
        "hd": gif.urls.hd,
        "sd": gif.urls.sd,
        "api": f"/v1/gifs/{gif.id}/download?quality=hd",
        "cli": f"aioredgif pull {SITE}/watch/{gif.id}",
    }
    return record


def _orientation(width: object, height: object) -> str | None:
    if not (isinstance(width, (int, float)) and isinstance(height, (int, float)) and width and height):
        return None
    ratio = width / height
    return "square" if 0.9 <= ratio <= 1.1 else "portrait" if ratio < 1 else "landscape"


def _shape_of(post: dict) -> str:
    return post.get("orientation") or _orientation(post.get("width"), post.get("height")) or "unknown"


def _number_stats(values: list[float]) -> dict | None:
    if not values:
        return None
    return {
        "total": round(sum(values), 2),
        "mean": round(statistics.fmean(values), 2),
        "median": round(statistics.median(values), 2),
        "min": min(values),
        "max": max(values),
    }


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def analyse(posts: list[dict]) -> dict:
    """Summary statistics for a set of post records.

    Args:
        posts: Records as made by :func:`post_record` or found in sidecars.

    Returns:
        Counts by type, orientation and resolution; duration and engagement
        statistics; tag, tag-pair and niche rankings (with first and last use
        of each tag); an upload timeline by month, weekday and hour (UTC);
        the most viewed and most liked posts; and library coverage.
    """
    stats = compute_stats(posts)
    stats.pop("_by_tag")
    stats.pop("_by_niche")
    videos = [post for post in posts if post.get("type") != "image"]
    durations = [post["duration_s"] for post in videos if isinstance(post.get("duration_s"), (int, float))]
    views = [post["views"] for post in posts if isinstance(post.get("views"), (int, float))]
    likes = [post["likes"] for post in posts if isinstance(post.get("likes"), (int, float))]
    times = sorted((moment, post) for post in posts if (moment := _parse_time(post.get("created"))))

    tag_dates: dict[str, list[datetime]] = {}
    for moment, post in times:
        for tag in post.get("tags") or []:
            tag_dates.setdefault(tag, []).append(moment)
    for entry in stats["tags"]:
        seen = tag_dates.get(entry["tag"])
        entry["first_used"] = seen[0].isoformat() if seen else None
        entry["last_used"] = seen[-1].isoformat() if seen else None

    resolutions = Counter(
        f"{post['width']}x{post['height']}" for post in posts if post.get("width") and post.get("height")
    )
    gaps = [(later[0] - earlier[0]).total_seconds() / 86400 for earlier, later in zip(times, times[1:], strict=False)]

    def top(key: str) -> list[dict]:
        ranked = sorted((post for post in posts if isinstance(post.get(key), (int, float))), key=lambda p: -p[key])
        return [{"id": post["id"], key: post[key], "page_url": post.get("page_url")} for post in ranked[:10]]

    total_views, total_likes = sum(views), sum(likes)
    return {
        "posts": len(posts),
        "videos": len(videos),
        "images": len(posts) - len(videos),
        "with_audio": sum(1 for post in videos if post.get("has_audio")),
        "orientation": dict(Counter(_shape_of(post) for post in posts)),
        "resolutions": [{"resolution": res, "count": count} for res, count in resolutions.most_common(10)],
        "duration_s": _number_stats(durations),
        "views": _number_stats(views),
        "likes": _number_stats(likes),
        "like_rate": round(total_likes / total_views, 5) if total_views else None,
        "unique_tags": stats["unique_tags"],
        "tags_per_post": round(sum(len(post.get("tags") or []) for post in posts) / len(posts), 2) if posts else 0,
        "tags": stats["tags"],
        "tag_pairs": stats["tag_pairs"],
        "niches": stats["niches"],
        "timeline": {
            "first_upload": times[0][0].isoformat() if times else None,
            "last_upload": times[-1][0].isoformat() if times else None,
            "active_days": round((times[-1][0] - times[0][0]).total_seconds() / 86400, 1) if len(times) > 1 else 0,
            "mean_days_between_uploads": round(statistics.fmean(gaps), 2) if gaps else None,
            "by_month": dict(sorted(Counter(moment.strftime("%Y-%m") for moment, _ in times).items())),
            "by_weekday": {day: sum(1 for m, _ in times if m.weekday() == i) for i, day in enumerate(WEEKDAYS)},
            "by_hour_utc": {f"{hour:02d}": sum(1 for m, _ in times if m.hour == hour) for hour in range(24)},
        },
        "most_viewed": top("views"),
        "most_liked": top("likes"),
        "in_library": sum(1 for post in posts if post.get("file")),
        "total_bytes_in_library": sum(post.get("bytes") or 0 for post in posts if post.get("file")),
    }


def build_report(profile: dict, posts: list[dict], source: str, complete: bool) -> dict:
    """Assemble a report document.

    Args:
        profile: From :func:`normalise_profile`.
        posts: Post records.
        source: ``"redgifs"`` (fetched live) or ``"library"`` (from local files).
        complete: False when the post list was cut short by a limit.
    """
    return {
        "schema": SCHEMA,
        "generated": datetime.now(UTC).isoformat(),
        "generator": f"aioredgif {__version__}",
        "source": source,
        "complete": complete,
        "creator": profile,
        "summary": analyse(posts),
        "posts": posts,
    }


async def creator_report(
    client: RedGifsClient,
    username: str,
    limit: int = 1000,
    library: Library | None = None,
    on_progress: object = None,
) -> dict:
    """Build a creator report from RedGIFs.

    Args:
        client: The RedGIFs client.
        username: The creator's handle (from their profile link).
        limit: Most posts to read.
        library: When given, each post records whether and where it is downloaded.
        on_progress: Optional callable ``(posts_read, total_or_None)``.

    Returns:
        The report document (see :func:`build_report`).

    Raises:
        RedGifsError: When the creator cannot be found or RedGIFs keeps failing.
    """
    username = username.strip().lstrip("@")
    raw_profile: dict = {}
    try:
        answer = await client.user(username)
        raw_profile = answer.get("user", answer) if isinstance(answer, dict) else {}
    except RedGifsError as exc:
        if exc.status not in (400, 404):
            raise
    posts: list[dict] = []
    total = None
    page = 1
    root = library.root if library else None
    while len(posts) < limit:
        result = await client.user_gifs(username, page, 80, "new")
        total = result.total or total
        if not raw_profile:
            raw_profile = next((u for u in result.users if (u.get("username") or "").lower() == username.lower()), {})
        posts += [post_record(gif, library, root) for gif in result.items[: limit - len(posts)]]
        if callable(on_progress):
            on_progress(len(posts), total)
        if not result.items or page >= result.pages:
            break
        page += 1
    if not posts and not raw_profile:
        raise RedGifsError(404, f"no creator called {username!r}")
    return build_report(normalise_profile(raw_profile, username), posts, "redgifs", complete=len(posts) >= (total or 0))


def library_reports(library: Library) -> dict[str, dict]:
    """Reports for every creator in the library, built offline from sidecars.

    Profiles are minimal (only what sidecars hold); run an online report for
    follower counts, avatars and the like.
    """
    by_creator: dict[str, list[dict]] = {}
    for gif_id in library.ids():
        entry = library.entry(gif_id)
        if not entry:
            continue
        by_creator.setdefault(entry["creator"], []).append(library_record(library, entry))
    return {
        creator: build_report(normalise_profile({}, creator), posts, "library", complete=False)
        for creator, posts in sorted(by_creator.items())
    }


def library_record(library: Library, entry: dict) -> dict:
    """A post record for a library item: its sidecar if it has one, else what the file tells us."""
    path = Path(entry["path"])
    sidecar = path.with_suffix(".json")
    record: dict = {}
    if sidecar.exists():
        try:
            record = json.loads(sidecar.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            record = {}
    record.pop("raw", None)
    record.setdefault("id", entry["id"])
    record.setdefault("creator", entry["creator"])
    record.setdefault("tags", entry["tags"])
    record.setdefault("niches", entry["niches"])
    record.setdefault("type", "image" if entry["image"] else "video")
    record.setdefault("page_url", f"{SITE}/watch/{entry['id']}")
    record["file"] = path.relative_to(library.root).as_posix()
    record["bytes"] = entry["bytes"]
    record["orientation"] = _orientation(record.get("width"), record.get("height"))
    return record


def flatten(posts: Iterable[dict]) -> list[dict]:
    """Posts as flat rows for CSV: one value per column, lists joined with ``;``."""
    columns = [
        "id", "creator", "type", "created", "duration_s", "width", "height", "orientation", "has_audio",
        "views", "likes", "tags", "niches", "description", "page_url", "file", "bytes",
    ]  # fmt: skip
    rows = []
    for post in posts:
        row = {column: post.get(column) for column in columns}
        row["tags"] = ";".join(post.get("tags") or [])
        row["niches"] = ";".join(post.get("niches") or [])
        media = post.get("media") or post.get("download") or {}
        row["hd_url"] = media.get("hd")
        row["sd_url"] = media.get("sd")
        row["thumbnail_url"] = media.get("thumbnail") or media.get("poster")
        rows.append(row)
    return rows
