"""Read-only RedGIFs lookups: posts, creators, tags, niches and link resolving."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from aioredgif.api.deps import client, upstream_error
from aioredgif.client import RedGifsError
from aioredgif.creators import creator_report
from aioredgif.downloader import ext_of, pick_url
from aioredgif.models import Gif, Order, Page, Quality, ResolveRequest, ResolveResult
from aioredgif.parsing import classify_url
from aioredgif.ratelimit import rate_limit

router = APIRouter(prefix="/v1", tags=["RedGIFs lookups"], dependencies=[Depends(rate_limit)])


@router.get("/gifs/{gif_id}", response_model=Gif)
async def get_gif(gif_id: str, request: Request) -> Gif:
    """One post: tags, creator, stats and media URLs."""
    try:
        return await client(request).gif(gif_id)
    except RedGifsError as exc:
        raise upstream_error(exc) from exc


@router.get("/gifs/{gif_id}/download")
async def download_gif(gif_id: str, request: Request, quality: Quality = "hd") -> StreamingResponse:
    """Stream one post's file straight through to the caller, without storing it."""
    redgifs = client(request)
    try:
        gif = await redgifs.gif(gif_id)
    except RedGifsError as exc:
        raise upstream_error(exc) from exc
    url = pick_url(gif, quality)
    if not url:
        raise HTTPException(404, "no media url")

    stream = redgifs.stream(url)
    response = await stream.__aenter__()
    if response.status_code != 200:
        await stream.__aexit__(None, None, None)
        raise HTTPException(502, f"media fetch failed: {response.status_code}")

    async def body() -> AsyncIterator[bytes]:
        try:
            async for chunk in response.aiter_bytes(1 << 16):
                yield chunk
        finally:
            await stream.__aexit__(None, None, None)

    headers = {"Content-Disposition": f'attachment; filename="{gif.id}.{ext_of(url)}"'}
    if "content-length" in response.headers:
        headers["Content-Length"] = response.headers["content-length"]
    return StreamingResponse(body(), media_type=response.headers.get("content-type", "video/mp4"), headers=headers)


@router.get("/users/{username}/gifs", response_model=Page)
async def user_gifs(
    username: str,
    request: Request,
    page: int = Query(1, ge=1),
    count: int = Query(40, ge=1, le=80),
    order: Order = "new",
) -> Page:
    """One page of a creator's posts. Use the handle from the profile URL, not the display name."""
    try:
        return await client(request).user_gifs(username, page, count, order)
    except RedGifsError as exc:
        raise upstream_error(exc) from exc


@router.get("/users/{username}/report")
async def user_report(
    username: str,
    request: Request,
    limit: int = Query(200, ge=1, le=2000, description="Most posts to read"),
    posts: bool = Query(True, description="Include every post, not just the summary"),
) -> dict:
    """Everything public about a creator: profile, every post, and an analysis.

    Profile: handle, display name, profile image, description, followers,
    views, post count, join date, links. Posts: upload date, size, duration,
    views, likes, tags, niches, media URLs and how to download each. Analysis:
    totals, top tags with first/last use, tag pairs, upload timeline, most
    viewed and liked posts, library coverage. Schema: ``aioredgif.creator/1``
    (see docs/DATA.md).
    """
    try:
        report = await creator_report(client(request), username, limit, request.app.state.library)
    except RedGifsError as exc:
        raise upstream_error(exc) from exc
    if not posts:
        report.pop("posts")
    return report


@router.get("/search", response_model=Page)
async def search(
    request: Request,
    tags: str = Query(..., description="Comma separated tags, e.g. 'blonde,solo'"),
    page: int = Query(1, ge=1),
    count: int = Query(40, ge=1, le=80),
    order: Order = "trending",
) -> Page:
    """One page of posts carrying all the given tags."""
    tag_list = [tag.strip().lstrip("#") for tag in tags.split(",") if tag.strip()]
    try:
        return await client(request).search(tag_list, page, count, order)
    except RedGifsError as exc:
        raise upstream_error(exc) from exc


@router.get("/niches/{niche}")
async def niche_info(niche: str, request: Request) -> dict:
    """A niche's name, description and counts."""
    try:
        return await client(request).niche(niche)
    except RedGifsError as exc:
        raise upstream_error(exc) from exc


@router.get("/niches/{niche}/gifs", response_model=Page)
async def niche_gifs(
    niche: str,
    request: Request,
    page: int = Query(1, ge=1),
    count: int = Query(40, ge=1, le=80),
    order: Order = "trending",
) -> Page:
    """One page of a niche's feed."""
    try:
        return await client(request).niche_gifs(niche, page, count, order)
    except RedGifsError as exc:
        raise upstream_error(exc) from exc


@router.post("/resolve", response_model=ResolveResult)
async def resolve(body: ResolveRequest, request: Request) -> ResolveResult:
    """Turn any RedGIFs link (watch, creator, niche, tag or media) into post ids and media URLs.

    Set ``use_browser`` to use the Playwright fallback, which reads the page the
    way DevTools' Network tab would.
    """
    kind, value = classify_url(body.url)
    redgifs = client(request)
    browser = request.app.state.browser
    try:
        if kind == "watch":
            if not body.use_browser:
                try:
                    gif = await redgifs.gif(value)
                    urls = [url for url in (gif.urls.hd, gif.urls.sd) if url]
                    return ResolveResult(kind="watch", ids=[gif.id], user_name=gif.user_name, media_urls=urls)
                except RedGifsError as exc:
                    if not browser or exc.status == 404:
                        raise
            if not browser:
                raise HTTPException(503, "browser fallback disabled")
            info = await browser.watch(value)
            urls = [url for url in (info["hd"], info["sd"]) if url] or info["captured"]
            return ResolveResult(kind="watch", ids=[value], method="browser", media_urls=urls)
        if kind == "creator":
            if body.use_browser and browser:
                ids = await browser.creator_ids(value)
                return ResolveResult(kind="creator", ids=ids, user_name=value, method="browser")
            page = await redgifs.user_gifs(value, 1, 80)
            return ResolveResult(kind="creator", ids=[gif.id for gif in page.items], user_name=value)
        if kind == "niche":
            page = await redgifs.niche_gifs(value, 1, 80)
            return ResolveResult(kind="niche", ids=[gif.id for gif in page.items], niche=value)
        if kind == "tag":
            page = await redgifs.search([value], 1, 80)
            return ResolveResult(kind="tag", ids=[gif.id for gif in page.items], tag=value)
    except RedGifsError as exc:
        raise upstream_error(exc) from exc
    raise HTTPException(400, "Not a recognised RedGIFs URL")
