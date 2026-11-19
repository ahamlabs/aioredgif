"""Helpers shared by the routers: app state accessors and error mapping."""

from __future__ import annotations

from fastapi import HTTPException, Request

from aioredgif.client import RedGifsClient, RedGifsError
from aioredgif.downloader import JobManager
from aioredgif.faves import CID_RE
from aioredgif.models import JobStatus


def client(request: Request) -> RedGifsClient:
    """The RedGIFs client of this app."""
    return request.app.state.client


def jobs(request: Request) -> JobManager:
    """The job manager of this app."""
    return request.app.state.jobs


def job_or_404(request: Request, job_id: str) -> JobStatus:
    """Look up a pull or answer 404."""
    job = request.app.state.jobs.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


def upstream_error(exc: RedGifsError) -> HTTPException:
    """Map a RedGIFs failure to an HTTP error for our caller."""
    return HTTPException(exc.status if exc.status in (400, 404, 429) else 502, str(exc))


def client_id(request: Request) -> str:
    """The browser's client id, from ``X-Client-Id`` or ``?c=``.

    Faves and rewards are kept per client id. The page makes one up and keeps it
    in local storage.

    Raises:
        HTTPException: 400 when it is missing or malformed.
    """
    cid = request.headers.get("X-Client-Id") or request.query_params.get("c") or ""
    if not CID_RE.match(cid):
        raise HTTPException(400, "missing or bad client id (X-Client-Id header or ?c=)")
    return cid
