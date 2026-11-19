"""Pausing pulls, picking up hand-copied files, and importing older versions' downloads."""

import asyncio
import json

import httpx
from conftest import make_handler, wait_for_job
from fastapi.testclient import TestClient

from aioredgif.app import create_app
from aioredgif.config import Settings

NICHE = {"urls": ["https://www.redgifs.com/niches/lost-bet-captions"]}


def test_pause_then_resume(api, monkeypatch):
    tc, _, tmp = api
    import aioredgif.downloader as downloader

    real = downloader.download_one

    async def slow_download(*args, **kwargs):
        await asyncio.sleep(0.4)
        return await real(*args, **kwargs)

    monkeypatch.setattr(downloader, "download_one", slow_download)
    job = tc.post("/v1/jobs", json=NICHE).json()
    asyncio.run(asyncio.sleep(0.15))

    paused = tc.post(f"/v1/jobs/{job['id']}/pause")
    assert paused.status_code == 200
    status = wait_for_job(tc, job["id"])
    assert status["state"] == "paused"
    assert status["downloaded"] < 4
    assert tc.post(f"/v1/jobs/{job['id']}/pause").status_code == 409  # not running any more

    # Another pull can run meanwhile; then the paused one resumes and finishes.
    other = wait_for_job(tc, tc.post("/v1/jobs", json={"ids": ["silentvisibletarsier"]}).json()["id"])
    assert other["state"] == "done"
    assert tc.post(f"/v1/jobs/{job['id']}/resume").status_code == 202
    done = wait_for_job(tc, job["id"])
    assert done["state"] == "done" and done["downloaded"] == 4

    history = {item["id"]: item for item in tc.get("/v1/history").json()["items"]}
    assert history[job["id"]]["state"] == "done"


def test_paused_pulls_do_not_auto_resume(tmp_path):
    from aioredgif.downloader import source_key
    from aioredgif.models import JobRequest, JobState, JobStatus

    request = JobRequest(**NICHE)
    key, label = source_key(request)
    (tmp_path / ".jobs").mkdir()
    for job_id, state in (("pausedjob001", JobState.paused), ("brokenjob001", JobState.running)):
        job = JobStatus(
            id=job_id, state=state, request=request, created="2026-11-01T10:00:00", source_key=key + job_id, label=label
        )
        (tmp_path / ".jobs" / f"{job_id}.json").write_text(job.model_dump_json())
    calls = []
    settings = Settings(download_dir=tmp_path, upstream_min_interval=0, browser_enabled=False)
    with TestClient(create_app(settings, transport=httpx.MockTransport(make_handler(calls)))) as tc:
        assert wait_for_job(tc, "brokenjob001")["state"] == "done"  # interrupted: resumed on start
        assert tc.get("/v1/jobs/pausedjob001").json()["state"] == "paused"  # paused: left alone


def test_library_picks_up_hand_copied_files_at_any_depth(api):
    tc, _, tmp = api
    assert tc.get("/v1/library").json()["total"] == 0
    deep = tmp / "library" / "old-stuff" / "someone" / "deepclip.mp4"
    deep.parent.mkdir(parents=True)
    deep.write_bytes(b"\x00" * 500)
    loose = tmp / "library" / "Loose Clip.MP4"
    loose.write_bytes(b"\x00" * 300)
    image = tmp / "library" / "someone" / "pic.jpg"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"\xff\xd8 not really a jpeg")

    lib = tc.get("/v1/library").json()  # rescans by itself (interval is 0 in tests)
    assert lib["total"] == 3
    by_id = {item["id"]: item for item in lib["items"]}
    assert by_id["deepclip"]["creator"] == "someone"
    assert by_id["loose clip"]["creator"] == "unsorted"
    assert by_id["pic"]["image"] is True
    assert tc.get(by_id["loose clip"]["play"], headers={"Range": "bytes=0-9"}).status_code == 206
    assert tc.get(by_id["pic"]["thumb"]).content.startswith(b"\xff\xd8")  # images are their own thumbnail
    assert tc.get("/v1/library", params={"kind": "image"}).json()["total"] == 1
    assert tc.post("/v1/library/rescan").json() == {"indexed": 3}


def test_older_version_downloads_are_imported(tmp_path):
    """Before 1.0, files lived in downloads/<job>/<creator>/ and history was not saved."""
    old_job = tmp_path / "a1b2c3d4e5f6"
    (old_job / "maker0").mkdir(parents=True)
    (old_job / "maker0" / "oldclip.mp4").write_bytes(b"\x00" * 800)
    (old_job / "maker0" / "oldclip.json").write_text(
        json.dumps(
            {
                "id": "oldclip",
                "creator": "maker0",
                "tags": ["Vintage"],
                "duration_s": 7,
                "media": {"thumbnail": "https://media.redgifs.com/OldClip-mobile.jpg"},
            }
        )
    )
    (old_job / "metadata.json").write_text(
        json.dumps(
            {
                "job": {
                    "id": old_job.name,
                    "created": "2026-11-10T12:00:00",
                    "request": {"urls": ["https://www.redgifs.com/users/maker0"]},
                },
                "items": [
                    {
                        "id": "oldclip",
                        "creator": "maker0",
                        "tags": ["Vintage"],
                        "file": "maker0/oldclip.mp4",
                        "media": {"thumbnail": "https://media.redgifs.com/OldClip-mobile.jpg"},
                    }
                ],
            }
        )
    )
    calls = []
    settings = Settings(download_dir=tmp_path, upstream_min_interval=0, browser_enabled=False)
    with TestClient(create_app(settings, transport=httpx.MockTransport(make_handler(calls)))) as tc:
        lib = tc.get("/v1/library").json()
        assert lib["total"] == 1 and lib["items"][0]["tags"] == ["Vintage"]
        history = tc.get("/v1/history").json()["items"]
        assert history[0]["id"] == old_job.name and history[0]["imported"] is True
        assert history[0]["downloaded"] == 1
        assert tc.get(f"/v1/jobs/{old_job.name}/archive").status_code == 200

        # Forgetting it sticks across restarts.
        assert tc.delete(f"/v1/history/{old_job.name}").status_code == 204
    with TestClient(create_app(settings, transport=httpx.MockTransport(make_handler(calls)))) as tc:
        assert tc.get("/v1/history").json()["items"] == []
        assert tc.get("/v1/library").json()["total"] == 1  # the clip itself stays
