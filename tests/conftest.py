"""Shared fixtures: an aioredgif app wired to a fake RedGIFs (no network)."""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from aioredgif.app import create_app
from aioredgif.config import Settings

GIF = {
    "id": "silentvisibletarsier",
    "userName": "paul57ak57",
    "tags": ["Blonde"],
    "type": 1,
    "createDate": 1785286188,
    "duration": 4.2,
    "width": 1080,
    "height": 1920,
    "hasAudio": False,
    "urls": {
        "hd": "https://media.redgifs.com/SilentVisibleTarsier.mp4",
        "sd": "https://media.redgifs.com/SilentVisibleTarsier-mobile.mp4",
        "poster": "https://media.redgifs.com/SilentVisibleTarsier-poster.jpg",
        "thumbnail": "https://media.redgifs.com/SilentVisibleTarsier-mobile.jpg",
    },
}


PROFILE = {
    "username": "paul57ak57",
    "name": "JuliaBNWO",
    "profileImageUrl": "https://userpic.redgifs.com/9/19/9197ef759fa20bfb7fa08b70b5cd1994.png",
    "description": "test profile",
    "followers": 81,
    "views": 74100,
    "publishedGifs": 6,
    "verified": False,
    "creationtime": 1770000000,
}


def make_handler(calls):
    state = {"n429": 1, "token": 0}

    def handler(req: httpx.Request):
        calls.append(req.url.path)
        p = req.url.path
        if req.url.host == "media.redgifs.com":
            assert req.headers["referer"] == "https://www.redgifs.com/"
            if p.endswith(".jpg"):
                return httpx.Response(200, content=b"\xff\xd8JPEG", headers={"content-type": "image/jpeg"})
            body = bytes(range(256)) * 4
            rng = req.headers.get("range")
            if rng:
                start = int(rng.split("=")[1].split("-")[0])
                if start >= len(body):
                    return httpx.Response(416)
                return httpx.Response(
                    206,
                    content=body[start:],
                    headers={
                        "content-type": "video/mp4",
                        "content-range": f"bytes {start}-{len(body) - 1}/{len(body)}",
                    },
                )
            return httpx.Response(200, content=body[:1000], headers={"content-type": "video/mp4"})
        if p == "/v2/auth/temporary":
            state["token"] += 1
            return httpx.Response(200, json={"token": f"t{state['token']}"})
        assert req.headers["authorization"].startswith("Bearer t")
        if p == "/v2/gifs/silentvisibletarsier":
            if state["n429"]:
                state["n429"] -= 1
                return httpx.Response(429, headers={"Retry-After": "0"})
            return httpx.Response(200, json={"gif": GIF})
        if p == "/v2/gifs/nope":
            return httpx.Response(404, json={"error": {"message": "gone"}})
        if p == "/v1/users/paul57ak57":
            return httpx.Response(200, json=PROFILE)
        if p.startswith("/v1/users/"):
            return httpx.Response(404, json={"error": {"message": "user not found"}})
        if p == "/v2/users/paul57ak57/search":
            page = int(req.url.params["page"])
            gifs = [
                dict(
                    GIF,
                    id=f"gif{page}{'abcdefgh'[i]}",
                    createDate=1780000000 + (page * 3 + i) * 86400 * 3,
                    views=100 * (page * 3 + i),
                    likes=10 * (page + i),
                    tags=["Blonde", "Solo"] if i == 0 else ["Blonde"],
                    type=2 if (page, i) == (2, 2) else 1,
                )
                for i in range(3)
            ]
            return httpx.Response(200, json={"gifs": gifs, "page": page, "pages": 2, "total": 6, "users": [PROFILE]})
        if p == "/v2/gifs":
            ids = req.url.params["ids"].split(",")
            return httpx.Response(
                200, json={"gifs": [dict(GIF, id=i, userName="maker0", tags=["Captions"]) for i in ids]}
            )
        if p == "/v2/niches/lost-bet-captions/gifs":
            tagsets = [["Captions", "Blonde"], ["Captions"], ["Captions", "Solo"], ["Blonde", "Solo"]]
            gifs = [
                dict(
                    GIF,
                    id=f"niche{'abcd'[i]}clip",
                    userName=f"maker{i % 2}",
                    tags=tagsets[i],
                    niches=["lost-bet-captions"],
                    duration=5,
                )
                for i in range(4)
            ]
            return httpx.Response(200, json={"gifs": gifs, "page": 1, "pages": 1, "total": 4})
        if p == "/v2/gifs/search":
            return httpx.Response(200, json={"gifs": [GIF], "page": 1, "pages": 1, "total": 1})
        if req.url.host == "media.redgifs.com":
            return httpx.Response(200, content=b"\x00" * 1000, headers={"content-type": "video/mp4"})
        return httpx.Response(500)

    return handler


@pytest.fixture
def api(tmp_path, monkeypatch):
    """A running app with its own download folder. Yields ``(test_client, upstream_calls, download_dir)``."""
    monkeypatch.setattr("aioredgif.client.backoff", lambda attempt: 0)
    monkeypatch.setattr("aioredgif.downloader.backoff", lambda attempt: 0)
    calls = []
    settings = Settings(
        download_dir=tmp_path,
        upstream_min_interval=0,
        browser_enabled=False,
        free_rpm=10_000,
        library_rescan_seconds=0,
    )
    app = create_app(settings, transport=httpx.MockTransport(make_handler(calls)))
    with TestClient(app) as test_client:
        yield test_client, calls, tmp_path


def wait_for_job(test_client, job_id, timeout=5.0):
    """Poll a pull until it leaves the queued/running states."""
    loop_until = timeout / 0.03
    status = None
    for _ in range(int(loop_until)):
        status = test_client.get(f"/v1/jobs/{job_id}").json()
        if status["state"] not in ("queued", "running"):
            return status
        asyncio.run(asyncio.sleep(0.03))
    return status
