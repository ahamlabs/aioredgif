"""The library: browse, play and zip every clip ever pulled, across sessions."""

from __future__ import annotations

import random
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from aioredgif.api.responses import media_file, with_sidecars, zip_files
from aioredgif.creators import library_reports
from aioredgif.exports import MEDIA_TYPES, library_posts, render
from aioredgif.library import Library
from aioredgif.tagfilter import TagFilter, split_tags
from aioredgif.thumbs import ThumbnailError, media_type

router = APIRouter(prefix="/v1/library", tags=["Library"])

SORTS = {
    "stashed": (lambda entry: entry["stashed"], True),
    "creator": (lambda entry: ((entry["creator"] or "").lower(), entry["id"]), False),
    "longest": (lambda entry: entry["duration_s"] or 0, True),
    "shortest": (lambda entry: entry["duration_s"] or 0, False),
    "views": (lambda entry: entry["views"] or 0, True),
}
KIND = Query("all", pattern="^(all|video|image)$")
INCLUDE = Query("", description="Comma separated tags to keep, e.g. 'blonde,solo'")
EXCLUDE = Query("", description="Comma separated tags to drop; exclusion wins")
MATCH = Query("any", pattern="^(any|all)$", description="Keep items with any or all included tags")


def _tag_filter(include: str, exclude: str, match: str) -> TagFilter:
    return TagFilter(split_tags(include), split_tags(exclude), match)


def _library(request: Request) -> Library:
    library: Library = request.app.state.library
    library.refresh()  # pick up files copied in by hand
    return library


def _public(entry: dict) -> dict:
    """An entry as the API shows it: no server paths, plus play/download/thumb URLs."""
    out = {key: value for key, value in entry.items() if key not in ("path", "thumb_src")}
    ref = quote(entry["id"], safe="")
    out["play"] = f"/v1/library/{ref}/file"
    out["dl"] = f"/v1/library/{ref}/file?download=true"
    out["thumb"] = f"/v1/library/{ref}/thumb"
    return out


@router.get("")
async def browse(
    request: Request,
    q: str = "",
    creator: str = "",
    tag: str = "",
    kind: str = KIND,
    include: str = INCLUDE,
    exclude: str = EXCLUDE,
    match: str = MATCH,
    sort: str = Query("stashed", pattern="^(stashed|creator|longest|shortest|views|random)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(120, ge=1, le=1000),
) -> dict:
    """Browse the library. Filters combine; the creator and tag counts describe the filtered set.

    ``include``/``exclude``/``match`` filter by tags: for example
    ``include=blonde,solo&exclude=pov`` keeps items tagged blonde or solo
    unless they are also tagged pov; add ``match=all`` to require both.

    Returns:
        ``total``, ``total_bytes``, ``total_duration_s``, ``creators``, ``tags``
        (top 60) and one page of ``items``.
    """
    items = _library(request).search(q, creator, tag, kind, _tag_filter(include, exclude, match))
    if sort == "random":
        random.shuffle(items)
    else:
        key, reverse = SORTS[sort]
        items.sort(key=key, reverse=reverse)
    creators: dict[str, int] = {}
    tags: dict[str, int] = {}
    for entry in items:
        creators[entry["creator"]] = creators.get(entry["creator"], 0) + 1
        for item_tag in set(entry["tags"]):
            tags[item_tag] = tags.get(item_tag, 0) + 1
    return {
        "total": len(items),
        "images": sum(1 for entry in items if entry["image"]),
        "clips": sum(1 for entry in items if not entry["image"]),
        "offset": offset,
        "total_bytes": sum(entry["bytes"] for entry in items),
        "total_duration_s": round(sum(entry["duration_s"] or 0 for entry in items), 1),
        "creators": [
            {"creator": name, "count": count}
            for name, count in sorted(creators.items(), key=lambda pair: (-pair[1], pair[0] or ""))
        ],
        "tags": [
            {"tag": name, "count": count}
            for name, count in sorted(tags.items(), key=lambda pair: (-pair[1], pair[0]))[:60]
        ],
        "items": [_public(entry) for entry in items[offset : offset + limit]],
    }


@router.get("/export")
async def export(
    request: Request,
    format: str = Query("jsonl", pattern="^(json|jsonl|csv)$"),  # noqa: A002 - matches the query parameter
    q: str = "",
    creator: str = "",
    kind: str = KIND,
    include: str = INCLUDE,
    exclude: str = EXCLUDE,
    match: str = MATCH,
) -> StreamingResponse:
    """Every matching library item as structured data: JSON, JSON Lines or CSV.

    Each record is the clip's full sidecar (creator, tags, niches, upload date,
    size, duration, views, likes, media URLs, local file) without the raw
    upstream blob. Schema: ``aioredgif.posts/1`` (see docs/DATA.md).
    """
    posts = library_posts(_library(request), creator, _tag_filter(include, exclude, match), kind, q)
    name = "-".join(part for part in ("aioredgif", creator or "library") if part) + f".{format}"
    return StreamingResponse(
        render(posts, format),
        media_type=MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/creators")
async def creators(request: Request, posts: bool = False) -> dict:
    """A report for every creator in the library, built offline from local metadata.

    Same schema as ``/v1/users/{username}/report`` but without live profile data
    (followers, avatar and so on); use that endpoint for the full profile.
    """
    reports = library_reports(_library(request))
    if not posts:
        for report in reports.values():
            report.pop("posts")
    return {"creators": reports}


@router.post("/rescan")
async def rescan(request: Request) -> dict:
    """Re-read the download folder now, for files copied in by hand.

    The library also re-scans by itself every ``library_rescan_seconds``.
    """
    count = request.app.state.library.scan()
    return {"indexed": count}


@router.get("/archive")
async def archive(
    request: Request,
    q: str = "",
    creator: str = "",
    tag: str = "",
    kind: str = KIND,
    include: str = INCLUDE,
    exclude: str = EXCLUDE,
    match: str = MATCH,
) -> FileResponse:
    """Everything matching the filters (with JSON sidecars) as one .zip. Takes the same filters as browsing."""
    items = _library(request).search(q, creator, tag, kind, _tag_filter(include, exclude, match))
    if not items:
        raise HTTPException(404, "nothing in the library matches")
    name = "-".join(part for part in ("library", creator, tag, q) if part) + ".zip"
    return zip_files(with_sidecars(Path(entry["path"]) for entry in items), name)


@router.get("/{gif_id}/file")
async def library_file(gif_id: str, request: Request, download: bool = False) -> FileResponse:
    """Play (default) or download one clip or image. Range is supported."""
    entry = _library(request).entry(gif_id)
    if not entry:
        raise HTTPException(404, "not in the library")
    return media_file(Path(entry["path"]), inline=not download)


@router.get("/{gif_id}/thumb")
async def library_thumb(gif_id: str, request: Request) -> FileResponse:
    """A thumbnail: the image itself for image posts, else the cached RedGIFs poster.

    Files copied in without metadata have no poster; the page then shows a frame
    of the video instead.
    """
    entry = _library(request).entry(gif_id)
    if not entry:
        raise HTTPException(404, "not in the library")
    if entry["image"]:
        return media_file(Path(entry["path"]), inline=True)
    try:
        path = await request.app.state.thumbs.get(entry["id"], entry["thumb_src"])
    except ThumbnailError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return FileResponse(path, media_type=media_type(path), headers={"Cache-Control": "public, max-age=604800"})
