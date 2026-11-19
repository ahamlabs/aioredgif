"""Pulls: start, watch, pause, resume, forget, and get their files and metadata."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from aioredgif.api.deps import job_or_404, jobs
from aioredgif.api.responses import media_file, with_sidecars, zip_files
from aioredgif.metadata import live_stats
from aioredgif.models import JobRequest, JobState, JobStatus
from aioredgif.parsing import classify_url
from aioredgif.ratelimit import rate_limit
from aioredgif.thumbs import ThumbnailError, media_type

router = APIRouter(prefix="/v1", tags=["Pulls"])
ACTIVE = (JobState.running, JobState.queued)


@router.post("/jobs", response_model=JobStatus, status_code=202)
async def create_job(body: JobRequest, request: Request, tier: str = Depends(rate_limit)) -> JobStatus:
    """Start a pull: give links, creators, niches, tags and/or ids; everything lands in the library.

    Sending the same link(s) again returns the same history entry (``reused``
    is true) and only fetches clips that are not in the library yet.
    """
    bad = [url for url in body.urls if classify_url(url)[0] == "unknown"]
    if bad:
        raise HTTPException(400, f"Not a RedGIFs creator, niche, tag or watch link: {bad[0]}")
    if tier == "free":
        cap = request.app.state.settings.free_max_items_per_job
        sources = len(body.users) + len(body.niches) + len(body.urls) + bool(body.tags) + bool(body.ids)
        body.limit_per_source = min(body.limit_per_source, max(1, cap // max(1, sources)))
    return jobs(request).submit(body)


@router.get("/jobs", response_model=list[JobStatus], dependencies=[Depends(rate_limit)])
async def list_jobs(request: Request) -> list[JobStatus]:
    """Every pull with full detail. For a lighter list, use ``/v1/history``."""
    return list(jobs(request).jobs.values())


@router.get("/jobs/{job_id}", response_model=JobStatus, dependencies=[Depends(rate_limit)])
async def job_status(job_id: str, request: Request) -> JobStatus:
    """A pull's progress, found posts and per-file results. Poll this while it runs."""
    return job_or_404(request, job_id)


@router.post("/jobs/{job_id}/pause", response_model=JobStatus)
async def pause_job(job_id: str, request: Request) -> JobStatus:
    """Stop a pull. Finished clips stay in the library; resume it whenever you like."""
    job = job_or_404(request, job_id)
    if job.state not in (*ACTIVE, JobState.interrupted):
        raise HTTPException(409, f"that pull is {job.state.value}, not running")
    return jobs(request).pause(job)


@router.post("/jobs/{job_id}/resume", response_model=JobStatus, status_code=202)
async def resume_job(job_id: str, request: Request, _: str = Depends(rate_limit)) -> JobStatus:
    """Continue a paused, interrupted or failed pull, or fetch new clips for a finished one."""
    return jobs(request).rerun(job_or_404(request, job_id))


@router.get("/history")
async def history(request: Request, limit: int = Query(100, ge=1, le=1000)) -> dict:
    """Every pull, newest first, as light summaries."""
    ordered = sorted(jobs(request).jobs.values(), key=lambda job: job.last_run or job.created, reverse=True)
    return {
        "items": [
            {
                "id": job.id,
                "label": job.label,
                "urls": job.request.urls,
                "state": job.state,
                "runs": job.runs,
                "created": job.created,
                "last_run": job.last_run,
                "finished": job.finished,
                "discovered": job.discovered,
                "downloaded": job.downloaded,
                "failed": job.failed,
                "already_had": job.already_had,
                "quality": job.request.quality,
                "imported": job.imported,
                "filtered_out": job.filtered_out,
                "tag_filter": job.request.tag_filter.describe(),
                "thumbs": [f"/v1/jobs/{job.id}/thumbs/{item.id}" for item in job.items[:4]],
            }
            for job in ordered[:limit]
        ]
    }


@router.delete("/history/{job_id}", status_code=204)
async def forget_job(job_id: str, request: Request) -> None:
    """Remove a pull from history. Its clips stay in the library (faves and other pulls may use them)."""
    job = job_or_404(request, job_id)
    if job.state in ACTIVE:
        raise HTTPException(409, "that pull is still running; pause it first")
    jobs(request).forget(job)


@router.get("/jobs/{job_id}/files/{gif_id}")
async def job_file(job_id: str, gif_id: str, request: Request, inline: bool = False) -> FileResponse:
    """One finished file. ``inline=true`` streams it for the player (Range supported)."""
    job = job_or_404(request, job_id)
    result = next((item for item in job.files if item.id == gif_id and item.path), None)
    if not result or not Path(result.path).exists():
        raise HTTPException(404, "file not downloaded yet")
    return media_file(Path(result.path), inline=inline)


@router.get("/jobs/{job_id}/archive")
async def job_archive(job_id: str, request: Request) -> FileResponse:
    """Everything a pull has stashed so far, plus its JSON metadata, as one .zip."""
    job = job_or_404(request, job_id)
    paths = [Path(item.path) for item in job.files if item.path and Path(item.path).exists()]
    if not paths:
        raise HTTPException(404, "no files downloaded yet")
    job_dir = jobs(request).root / job.id
    extras = [(path, path.name) for path in (job_dir / "metadata.json", job_dir / "tags.json") if path.exists()]
    owners = sorted({path.parent.name for path in paths})
    name = (owners[0] if len(owners) == 1 else "aioredgif") + f"-{job.id}.zip"
    return zip_files(with_sidecars(paths) + extras, name)


@router.get("/jobs/{job_id}/stats")
async def job_stats(job_id: str, request: Request) -> dict:
    """Tag, niche and creator counts, and the most common tag pairs. Works while the pull runs."""
    return live_stats(job_or_404(request, job_id))


@router.get("/jobs/{job_id}/metadata")
async def job_metadata(job_id: str, request: Request, kind: str = Query("all", pattern="^(all|tags)$")) -> FileResponse:
    """The JSON dump: ``kind=all`` gives metadata.json, ``kind=tags`` gives tags.json."""
    job = job_or_404(request, job_id)
    name = "metadata.json" if kind == "all" else "tags.json"
    path = jobs(request).root / job.id / name
    if not path.exists():
        raise HTTPException(409, "metadata is written when the pull finishes")
    return FileResponse(path, media_type="application/json", filename=f"{job.id}-{name}")


@router.get("/jobs/{job_id}/thumbs/{gif_id}")
async def job_thumb(job_id: str, gif_id: str, request: Request) -> FileResponse:
    """A post's thumbnail, fetched once through the server and cached."""
    job = job_or_404(request, job_id)
    item = next((item for item in job.items if item.id == gif_id), None)
    if not item:
        raise HTTPException(404, "no such post in this pull")
    try:
        path = await request.app.state.thumbs.get(gif_id, item.thumbnail)
    except ThumbnailError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return FileResponse(path, media_type=media_type(path), headers={"Cache-Control": "public, max-age=604800"})
