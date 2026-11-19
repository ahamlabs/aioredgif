"""Faves: clips a browser hearted, kept on the server so they survive restarts."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from aioredgif.api.deps import client_id
from aioredgif.api.responses import media_file
from aioredgif.faves import FaveStore
from aioredgif.thumbs import ThumbnailError, media_type

router = APIRouter(prefix="/v1/faves", tags=["Faves"])


def _store(request: Request) -> FaveStore:
    return request.app.state.faves


def _resolve(request: Request, record: dict) -> Path | None:
    """The fave's file: wherever the library has it now, else the path saved with it."""
    path = request.app.state.library.get(record["id"])
    if path:
        return path
    saved = Path(record.get("path") or "")
    return saved if saved.is_file() else None


def _public(record: dict, cid: str) -> dict:
    out = {key: value for key, value in record.items() if key not in ("path", "thumb_path")}
    ref = quote(record["id"], safe="")
    out["play"] = f"/v1/faves/{ref}/file?c={cid}"
    out["dl"] = f"/v1/faves/{ref}/file?download=true&c={cid}"
    out["thumb"] = f"/v1/faves/{ref}/thumb?c={cid}"
    return out


@router.get("")
async def list_faves(request: Request) -> dict:
    """This browser's faves, newest first. Send the ``X-Client-Id`` header."""
    cid = client_id(request)
    records = sorted(_store(request).load(cid).values(), key=lambda rec: rec.get("added", ""), reverse=True)
    return {"items": [_public(rec, cid) for rec in records if _resolve(request, rec)]}


@router.put("/{gif_id}")
async def add_fave(gif_id: str, request: Request) -> dict:
    """Fave any clip that is in the library. The body may carry ``{"job_id": ...}`` for reference."""
    cid = client_id(request)
    try:
        body = await request.json()
    except ValueError:
        body = {}
    entry = request.app.state.library.entry(gif_id)
    if not entry:
        raise HTTPException(404, "clip not in the library yet")
    record = await _store(request).add(
        cid,
        {
            "id": entry["id"],
            "user_name": entry["creator"],
            "tags": entry["tags"],
            "niches": entry["niches"],
            "job_id": (body or {}).get("job_id"),
            "path": entry["path"],
            "image": entry["image"],
            "width": entry["width"],
            "height": entry["height"],
        },
    )
    return _public(record, cid)


@router.delete("/{gif_id}", status_code=204)
async def remove_fave(gif_id: str, request: Request) -> None:
    """Un-fave a clip. The file stays in the library."""
    if not await _store(request).remove(client_id(request), gif_id):
        raise HTTPException(404, "not in faves")


@router.get("/{gif_id}/file")
async def fave_file(gif_id: str, request: Request, download: bool = False) -> FileResponse:
    """Play (default) or download a fave. Pass the client id as ``?c=`` for media tags."""
    record = _store(request).load(client_id(request)).get(gif_id.lower())
    path = _resolve(request, record) if record else None
    if not path:
        raise HTTPException(404, "not in faves")
    return media_file(path, inline=not download)


@router.get("/{gif_id}/thumb")
async def fave_thumb(gif_id: str, request: Request) -> FileResponse:
    """A fave's thumbnail."""
    record = _store(request).load(client_id(request)).get(gif_id.lower())
    if not record:
        raise HTTPException(404, "not in faves")
    entry = request.app.state.library.entry(gif_id)
    if entry and entry["image"]:
        return media_file(Path(entry["path"]), inline=True)
    try:
        path = await request.app.state.thumbs.get(gif_id.lower(), entry["thumb_src"] if entry else None)
    except ThumbnailError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return FileResponse(path, media_type=media_type(path), headers={"Cache-Control": "private, max-age=604800"})
