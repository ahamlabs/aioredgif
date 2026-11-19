"""Rewards: rank and badges for this browser."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from aioredgif.api.deps import client_id
from aioredgif.rewards import ProfileStore

router = APIRouter(prefix="/v1/me", tags=["Rewards"])


def _store(request: Request) -> ProfileStore:
    return request.app.state.profiles


@router.get("")
async def my_profile(request: Request) -> dict:
    """Rank, progress to the next rank, badges and totals. Send ``X-Client-Id``."""
    store = _store(request)
    return store.view(store.load(client_id(request)))


@router.post("/events")
async def report_activity(request: Request) -> dict:
    """Credit a batch of activity. The page sends one every 15 seconds.

    The body is a JSON object with any of ``seconds`` (capped at 30 per call),
    ``clips`` (ids watched), ``edge_holds``, ``stashed``, ``cave_opened``,
    ``cave_screens``, ``tag_filter`` and ``faves`` (current count).

    Returns:
        The profile, plus ``new_badges`` and ``rank_up`` when something was earned.
    """
    cid = client_id(request)
    try:
        event = await request.json()
    except ValueError:
        event = None
    if not isinstance(event, dict):
        raise HTTPException(400, "body must be a JSON object")
    try:
        return await _store(request).report(cid, event)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "bad event values") from exc
