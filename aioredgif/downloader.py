"""Pulls: collecting posts from RedGIFs and downloading them into the library.

A pull (a "job") is saved to ``<download_dir>/.jobs/<id>.json`` as it runs, so:

* the same link never downloads the same clip twice (repeat pulls share a
  history entry, and every clip already in the library is reused);
* a pull can be paused and resumed later;
* if the server stops mid-pull, the job is saved as ``interrupted`` and picked
  up on the next start, continuing half-downloaded files from the byte they
  stopped at.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from aioredgif.client import RedGifsClient, RedGifsError, backoff
from aioredgif.config import Settings
from aioredgif.library import Library
from aioredgif.metadata import write_job_metadata, write_sidecar
from aioredgif.models import FileResult, Gif, JobItem, JobRequest, JobState, JobStatus
from aioredgif.parsing import classify_url

log = logging.getLogger("aioredgif.downloader")

DOWNLOAD_ATTEMPTS = 4
FORGOTTEN_MARKER = ".forgotten"  # left in a job folder so a forgotten pull is not re-imported


def pick_url(gif: Gif, quality: str) -> str | None:
    """The media URL for ``quality``, falling back to the other one."""
    if quality == "hd":
        return gif.urls.hd or gif.urls.sd
    return gif.urls.sd or gif.urls.hd


def ext_of(url: str) -> str:
    """File extension of a media URL, ``"mp4"`` when it has none."""
    name = url.split("?", 1)[0].rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else "mp4"


async def download_one(client: RedGifsClient, gif: Gif, target: Path, quality: str) -> FileResult:
    """Download one post to ``target``.

    A leftover ``<target>.part`` from an earlier attempt is continued with an
    HTTP Range request instead of starting over.

    Args:
        client: The RedGIFs client (its throttle is shared).
        gif: The post.
        target: Final file path.
        quality: ``"hd"`` or ``"sd"``.

    Returns:
        The result, with ``error`` set when every attempt failed.
    """
    url = pick_url(gif, quality)
    if not url:
        return FileResult(id=gif.id, error="no media url")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        return FileResult(id=gif.id, path=str(target), bytes=target.stat().st_size, skipped=True)

    partial = target.with_suffix(target.suffix + ".part")
    for attempt in range(DOWNLOAD_ATTEMPTS):
        try:
            have = partial.stat().st_size if partial.exists() else 0
            headers = {"Range": f"bytes={have}-"} if have else {}
            async with client.throttle, client.stream(url, headers) as response:
                if response.status_code == 429:
                    raise RedGifsError(429, "rate limited")
                if response.status_code == 416:  # the .part file is already complete
                    partial.replace(target)
                    return FileResult(id=gif.id, path=str(target), bytes=target.stat().st_size)
                response.raise_for_status()
                append = have and response.status_code == 206
                with partial.open("ab" if append else "wb") as out:
                    async for chunk in response.aiter_bytes(1 << 16):
                        out.write(chunk)
            partial.replace(target)
            return FileResult(id=gif.id, path=str(target), bytes=target.stat().st_size)
        except asyncio.CancelledError:
            raise  # keep the .part file so the next run can continue it
        except Exception as exc:  # noqa: BLE001 - any failure is retried, then reported
            if attempt == DOWNLOAD_ATTEMPTS - 1:
                return FileResult(id=gif.id, error=str(exc))
            await asyncio.sleep(backoff(attempt))
    return FileResult(id=gif.id, error="unreachable")


def source_key(request: JobRequest) -> tuple[str, str]:
    """A stable key for "the same link(s)" and a short label for history.

    Two requests get the same key when they name the same sources with the same
    quality and image setting, however the links were written.

    Returns:
        ``(key, label)``.
    """
    parts: set[str] = set()
    for url in request.urls:
        kind, value = classify_url(url)
        kind = {"creator": "user", "watch": "id"}.get(kind, kind)
        parts.add(f"{kind}:{(value or '').lower()}")
    parts |= {f"user:{user.lower()}" for user in request.users}
    parts |= {f"niche:{niche.lower()}" for niche in request.niches}
    if request.tags:
        parts.add("tag:" + ",".join(sorted(tag.lower() for tag in request.tags)))
    parts |= {f"id:{gif_id.lower()}" for gif_id in request.ids}
    ordered = sorted(parts)
    key = "|".join(ordered) + f"#{request.quality}#{int(request.include_images)}"
    tag_filter = request.tag_filter
    if tag_filter.active:  # a different filter is a different pull
        key += "#" + tag_filter.key()
    label = ", ".join(ordered[:3]) + (f" +{len(ordered) - 3}" if len(ordered) > 3 else "")
    if tag_filter.active:
        label += f" ({tag_filter.describe()})"
    return key, label


class JobManager:
    """Runs, saves, pauses and resumes pulls.

    Jobs live in memory and in ``<download_dir>/.jobs``. For several server
    processes, swap this for a shared queue (Redis + RQ/Arq).

    Args:
        client: The RedGIFs client.
        settings: Server settings.
        library: The shared library.
    """

    def __init__(self, client: RedGifsClient, settings: Settings, library: Library) -> None:
        self.client = client
        self.settings = settings
        self.root = settings.download_dir
        self.library = library
        self.jobs_dir = self.root / ".jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, JobStatus] = {}
        self._download_slots = asyncio.Semaphore(settings.download_concurrency)
        self._tasks: dict[str, asyncio.Task] = {}
        self._pausing: set[str] = set()
        self._id_locks: dict[str, asyncio.Lock] = {}
        self._load()
        self.import_legacy()

    # ------------------------------------------------------------ persistence

    def _load(self) -> None:
        for path in self.jobs_dir.glob("*.json"):
            try:
                job = JobStatus.model_validate_json(path.read_text(encoding="utf-8"))
            except ValueError:
                log.warning("skipping unreadable job file %s", path)
                continue
            if job.state in (JobState.running, JobState.queued):
                job.state = JobState.interrupted
            job.reused = False
            self.jobs[job.id] = job

    def save(self, job: JobStatus) -> None:
        """Write a job to disk atomically."""
        path = self.jobs_dir / f"{job.id}.json"
        temp = path.with_suffix(".part")
        temp.write_text(job.model_dump_json(), encoding="utf-8")
        temp.replace(path)

    def import_legacy(self) -> list[str]:
        """Add pulls made by older versions (``<download_dir>/<job>/metadata.json``) to history.

        Their files are already indexed by the library; this only brings back
        the history entries so they can be opened, zipped or refreshed.

        Returns:
            The ids of the imported pulls.
        """
        imported = []
        for folder in sorted(self.root.iterdir()):
            meta_file = folder / "metadata.json"
            if (
                folder.name.startswith(".")
                or folder.name in self.jobs
                or not meta_file.exists()
                or (folder / FORGOTTEN_MARKER).exists()
            ):
                continue
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                request = JobRequest.model_validate(meta["job"]["request"])
                created = datetime.fromisoformat(meta["job"]["created"])
            except (ValueError, KeyError, TypeError):
                log.warning("could not import older pull from %s", folder)
                continue
            items, files = [], []
            for record in meta.get("items", []):
                media = record.get("media") or {}
                items.append(
                    JobItem(
                        id=record["id"],
                        user_name=record.get("creator"),
                        tags=record.get("tags") or [],
                        niches=record.get("niches") or [],
                        sources=record.get("found_via") or [],
                        thumbnail=media.get("thumbnail") or media.get("poster"),
                        width=record.get("width"),
                        height=record.get("height"),
                    )
                )
                path = self.library.get(record["id"])
                if path:
                    files.append(FileResult(id=record["id"], path=str(path), bytes=path.stat().st_size, skipped=True))
            key, label = source_key(request)
            job = JobStatus(
                id=folder.name,
                state=JobState.done,
                request=request,
                created=created,
                finished=created,
                last_run=created,
                discovered=len(items),
                items=items,
                files=files,
                downloaded=len(files),
                already_had=len(files),
                source_key=key,
                label=label,
                imported=True,
            )
            self.jobs[job.id] = job
            self.save(job)
            imported.append(job.id)
        if imported:
            log.info("imported %d pull(s) from an older version: %s", len(imported), imported)
        return imported

    # ------------------------------------------------------------- control

    def find_by_key(self, key: str) -> JobStatus | None:
        """The most recent pull for the same sources, if any."""
        same = [job for job in self.jobs.values() if job.source_key == key]
        return max(same, key=lambda job: job.created) if same else None

    def submit(self, request: JobRequest) -> JobStatus:
        """Start a pull, or reuse the history entry for the same link.

        If that pull is running, it is returned as is. Otherwise it runs again:
        clips already in the library are reused and only new ones download.
        """
        key, label = source_key(request)
        existing = self.find_by_key(key)
        if existing:
            existing.reused = True
            if existing.state in (JobState.running, JobState.queued):
                return existing
            existing.request.limit_per_source = max(existing.request.limit_per_source, request.limit_per_source)
            existing.request.order = request.order
            return self.rerun(existing)
        now = datetime.now()
        job = JobStatus(
            id=uuid.uuid4().hex[:12],
            state=JobState.queued,
            request=request,
            created=now,
            source_key=key,
            label=label,
            last_run=now,
        )
        self.jobs[job.id] = job
        self.save(job)
        self._start(job)
        return job

    def rerun(self, job: JobStatus) -> JobStatus:
        """Resume a paused/interrupted/failed pull, or refresh a finished one."""
        if job.id in self._tasks:
            return job
        if job.finished or job.files:
            job.runs += 1
        job.state = JobState.queued
        job.last_run = datetime.now()
        job.error = None
        self.save(job)
        self._start(job)
        return job

    def pause(self, job: JobStatus) -> JobStatus:
        """Stop a running pull. Finished clips stay; half-done files resume later."""
        task = self._tasks.get(job.id)
        if task and not task.done():
            self._pausing.add(job.id)
            task.cancel()
        elif job.state in (JobState.queued, JobState.interrupted):
            job.state = JobState.paused
            self.save(job)
        return job

    def forget(self, job: JobStatus) -> None:
        """Remove a pull from history. Its clips stay in the library."""
        self.jobs.pop(job.id, None)
        (self.jobs_dir / f"{job.id}.json").unlink(missing_ok=True)
        job_dir = self.root / job.id
        if job_dir.is_dir():
            (job_dir / FORGOTTEN_MARKER).touch()

    def resume_interrupted(self) -> list[str]:
        """Restart every pull the last shutdown interrupted (not paused ones)."""
        ids = [job.id for job in self.jobs.values() if job.state == JobState.interrupted]
        for job_id in ids:
            self.rerun(self.jobs[job_id])
        return ids

    async def shutdown(self) -> None:
        """Cancel running pulls; they are saved as interrupted."""
        for task in list(self._tasks.values()):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    def _start(self, job: JobStatus) -> None:
        task = asyncio.create_task(self._run(job))
        self._tasks[job.id] = task
        task.add_done_callback(lambda _task, job_id=job.id: self._tasks.pop(job_id, None))

    # -------------------------------------------------------------- running

    async def _collect(self, request: JobRequest) -> tuple[list[Gif], int]:
        """Gather posts from every source, then apply the request's filters.

        Returns:
            ``(posts to download, how many the tag filter removed)``.
        """
        for url in request.urls:
            kind, value = classify_url(url)
            if kind == "creator" and value.lower() not in request.users:
                request.users.append(value.lower())
            elif kind == "tag" and value not in request.tags:
                request.tags.append(value)
            elif kind == "niche" and value not in request.niches:
                request.niches.append(value)
            elif kind == "watch" and value not in request.ids:
                request.ids.append(value)
            elif kind == "unknown":
                raise ValueError(f"Not a RedGIFs creator, niche, tag or watch link: {url}")

        found: dict[str, Gif] = {}

        def add(gif: Gif, source: str) -> None:
            gif = found.setdefault(gif.id, gif)
            if source not in gif.sources:
                gif.sources.append(source)

        if request.ids:
            for gif in await self.client.gifs_by_ids(request.ids):
                add(gif, "id")
        for user in request.users:
            async for gif in self.client.iter_user(user, request.limit_per_source, request.order):
                add(gif, f"user:{user}")
        feed_order = "trending" if request.order == "new" else request.order
        for niche in request.niches:
            async for gif in self.client.iter_niche(niche, request.limit_per_source, feed_order):
                add(gif, f"niche:{niche}")
        if request.tags:
            async for gif in self.client.iter_search(request.tags, request.limit_per_source, feed_order):
                add(gif, "tag:" + ",".join(request.tags))
        gifs = list(found.values())
        if not request.include_images:
            gifs = [gif for gif in gifs if not gif.is_image]
        tag_filter = request.tag_filter
        kept = [gif for gif in gifs if tag_filter.matches(gif.tags)]
        return kept, len(gifs) - len(kept)

    async def _fetch(self, job: JobStatus, gif: Gif) -> FileResult:
        lock = self._id_locks.setdefault(gif.id, asyncio.Lock())
        async with lock:  # two pulls never download the same clip at once
            have = self.library.get(gif.id)
            if have:
                job.already_had += 1
                return FileResult(id=gif.id, path=str(have), bytes=have.stat().st_size, skipped=True)
            url = pick_url(gif, job.request.quality)
            target = self.library.target(gif, ext_of(url) if url else "mp4")
            async with self._download_slots:
                result = await download_one(self.client, gif, target, job.request.quality)
            if result.path:
                self.library.add(gif.id, Path(result.path))
            return result

    async def _run(self, job: JobStatus) -> None:
        job.state = JobState.running
        job.downloaded = job.failed = job.already_had = 0
        job.files = []
        job.finished = None
        self.save(job)
        try:
            gifs, job.filtered_out = await self._collect(job.request.model_copy(deep=True))
            job.discovered = len(gifs)
            job.items = [
                JobItem(
                    id=gif.id,
                    user_name=gif.user_name,
                    thumbnail=gif.urls.thumbnail or gif.urls.poster,
                    tags=gif.tags,
                    niches=gif.niches,
                    sources=gif.sources,
                    width=gif.width,
                    height=gif.height,
                )
                for gif in gifs
            ]
            job_dir = self.root / job.id
            job_dir.mkdir(parents=True, exist_ok=True)
            self.save(job)

            async def worker(gif: Gif) -> None:
                result = await self._fetch(job, gif)
                if not result.skipped or not Path(result.path).with_suffix(".json").exists():
                    write_sidecar(gif, result, self.root)
                job.files.append(result)
                if result.error:
                    job.failed += 1
                else:
                    job.downloaded += 1
                self.save(job)

            await asyncio.gather(*(worker(gif) for gif in gifs))
            write_job_metadata(job, gifs, job_dir, self.root)
            job.state = JobState.done
        except asyncio.CancelledError:
            if job.id in self._pausing:
                self._pausing.discard(job.id)
                job.state = JobState.paused
                log.info("pull %s paused", job.id)
            else:
                job.state = JobState.interrupted
                log.info("pull %s interrupted; it resumes on the next start", job.id)
                raise
        except Exception as exc:  # noqa: BLE001 - any failure ends the pull and is shown to the user
            log.exception("pull %s failed", job.id)
            job.state = JobState.failed
            job.error = str(exc)
        finally:
            if job.state not in (JobState.interrupted, JobState.paused):
                job.finished = datetime.now()
            self.save(job)
