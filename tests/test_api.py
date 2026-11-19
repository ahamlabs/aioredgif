"""API tests against a fake RedGIFs (see conftest.py)."""

import httpx
from conftest import wait_for_job

# The exact error RedGIFs returned in production.
BAD_SORT_MESSAGE = 'Bad sorting order "trending", must be one of: trending, oldest, latest, best, hot.'


def test_gif_metadata_with_429_retry(api):
    tc, calls, _ = api
    r = tc.get("/v1/gifs/silentvisibletarsier")
    assert r.status_code == 200, r.text
    assert r.json()["urls"]["hd"].endswith("SilentVisibleTarsier.mp4")
    assert calls.count("/v2/gifs/silentvisibletarsier") == 2  # one 429 then success
    assert calls.count("/v2/auth/temporary") == 1


def test_404(api):
    tc, *_ = api
    assert tc.get("/v1/gifs/nope").status_code == 404


def test_user_and_search(api):
    tc, *_ = api
    assert len(tc.get("/v1/users/paul57ak57/gifs").json()["items"]) == 3
    assert tc.get("/v1/search", params={"tags": "#blonde"}).json()["total"] == 1


def test_resolve_creator_url(api):
    tc, *_ = api
    r = tc.post("/v1/resolve", json={"url": "https://www.redgifs.com/users/paul57ak57"})
    assert r.json()["kind"] == "creator" and len(r.json()["ids"]) == 3


def test_stream_download(api):
    tc, *_ = api
    r = tc.get("/v1/gifs/silentvisibletarsier/download")
    assert r.status_code == 200 and len(r.content) == 1000
    assert "silentvisibletarsier.mp4" in r.headers["content-disposition"]


def test_bulk_job(api):
    tc, _, tmp = api
    r = tc.post("/v1/jobs", json={"users": ["@paul57ak57"], "tags": ["blonde"], "limit_per_source": 5})
    assert r.status_code == 202
    st = wait_for_job(tc, r.json()["id"])
    assert st["state"] == "done", st
    assert st["discovered"] == 6  # 5 from user (paged) + 1 from tag
    assert st["downloaded"] == 6
    assert len(list(tmp.rglob("*.mp4"))) == 6


def test_job_from_creator_link_and_zip(api):
    import io
    import zipfile

    tc, *_ = api
    r = tc.post("/v1/jobs", json={"urls": ["https://www.redgifs.com/users/paul57ak57"], "limit_per_source": 4})
    assert r.status_code == 202, r.text
    st = wait_for_job(tc, r.json()["id"])
    assert st["state"] == "done" and st["downloaded"] == 4 and len(st["items"]) == 4
    one = tc.get(f"/v1/jobs/{st['id']}/files/{st['items'][0]['id']}")
    assert one.status_code == 200 and len(one.content) == 1000
    z = tc.get(f"/v1/jobs/{st['id']}/archive")
    assert z.status_code == 200
    assert "paul57ak57" in z.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert len([n for n in names if n.endswith(".mp4")]) == 4
    assert len([n for n in names if n.endswith(".json") and "/" in n]) == 4  # sidecars


def test_bad_link_rejected(api):
    tc, *_ = api
    r = tc.post("/v1/jobs", json={"urls": ["https://example.com/users/x"]})
    assert r.status_code == 400


def test_frontend_served(api):
    tc, *_ = api
    r = tc.get("/")
    assert r.status_code == 200 and "Load up." in r.text
    assert tc.get("/fonts/archivo-latin-wdth-italic.woff2").status_code == 200
    imgs = tc.get("/v1/brand").json()["images"]
    assert all(i.startswith("/brand/") for i in imgs)  # README.txt is not listed
    assert tc.get("/health").json() == {"ok": True, "version": "1.0.0"}
    assert "aioredgif" in r.text and "/img/logo.png" in r.text
    for asset in ("/css/aioredgif.css", "/js/aioredgif.js", "/img/logo.png", "/favicon.ico", "/manifest.webmanifest"):
        assert tc.get(asset).status_code == 200, asset


def test_thumbnails_proxied_and_cached(api):
    tc, calls, tmp = api
    r = tc.post("/v1/jobs", json={"urls": ["https://www.redgifs.com/users/paul57ak57"], "limit_per_source": 2})
    st = wait_for_job(tc, r.json()["id"])
    gid = st["items"][0]["id"]
    assert st["items"][0]["thumbnail"].endswith("-mobile.jpg")
    t1 = tc.get(f"/v1/jobs/{st['id']}/thumbs/{gid}")
    assert t1.status_code == 200 and t1.headers["content-type"] == "image/jpeg"
    assert t1.content.startswith(b"\xff\xd8")
    n = calls.count("/SilentVisibleTarsier-mobile.jpg")
    tc.get(f"/v1/jobs/{st['id']}/thumbs/{gid}")
    assert calls.count("/SilentVisibleTarsier-mobile.jpg") == n  # served from cache
    assert (tmp / ".thumbs" / f"{gid}.jpg").exists()


def test_thumbnail_host_is_checked(api):
    tc, *_ = api
    from aioredgif.models import JobItem

    r = tc.post("/v1/jobs", json={"urls": ["https://www.redgifs.com/users/paul57ak57"], "limit_per_source": 1})
    st = wait_for_job(tc, r.json()["id"])
    job = tc.app.state.jobs.jobs[st["id"]]
    job.items[0] = JobItem(id=job.items[0].id, thumbnail="http://169.254.169.254/latest")
    assert tc.get(f"/v1/jobs/{st['id']}/thumbs/{job.items[0].id}").status_code == 400


def test_niche_job_writes_json_metadata(api):
    import io
    import json
    import zipfile

    tc, _, tmp = api
    r = tc.post("/v1/jobs", json={"urls": ["https://www.redgifs.com/niches/lost-bet-captions"]})
    assert r.status_code == 202, r.text
    st = wait_for_job(tc, r.json()["id"])
    assert st["state"] == "done" and st["downloaded"] == 4, st
    assert st["items"][0]["sources"] == ["niche:lost-bet-captions"]

    stats = tc.get(f"/v1/jobs/{st['id']}/stats").json()
    assert stats["tags"][0] == {"tag": "Captions", "count": 3, "share": 0.75}
    assert {"tags": ["Blonde", "Solo"], "count": 1} in stats["tag_pairs"]
    assert stats["niches"] == [{"niche": "lost-bet-captions", "count": 4}]

    meta = tc.get(f"/v1/jobs/{st['id']}/metadata?kind=all").json()
    assert meta["summary"]["posts"] == 4 and meta["summary"]["total_duration_s"] == 20
    item = meta["items"][0]
    assert item["file"].startswith("library/") and item["file"].endswith(".mp4")
    assert item["status"] == "saved" and item["raw"]["id"] == item["id"]

    tags = tc.get(f"/v1/jobs/{st['id']}/metadata?kind=tags").json()
    assert tags["tags"]["Captions"]["count"] == 3
    assert all(x["file"] for x in tags["tags"]["Solo"]["items"])
    assert tags["creators"] == {"maker0": 2, "maker1": 2}

    side = json.loads((tmp / "library" / "maker0" / "nicheaclip.json").read_text())
    assert side["tags"] == ["Captions", "Blonde"] and side["found_via"] == ["niche:lost-bet-captions"]

    names = zipfile.ZipFile(io.BytesIO(tc.get(f"/v1/jobs/{st['id']}/archive").content)).namelist()
    assert {"metadata.json", "tags.json", "maker0/nicheaclip.mp4", "maker0/nicheaclip.json"} <= set(names)


def test_niche_endpoints_and_resolve(api):
    tc, *_ = api
    assert tc.get("/v1/niches/lost-bet-captions/gifs").json()["total"] == 4
    r = tc.post("/v1/resolve", json={"url": "https://www.redgifs.com/niches/lost-bet-captions"}).json()
    assert r["kind"] == "niche" and len(r["ids"]) == 4


def test_metadata_before_finish_is_409(api):
    tc, *_ = api
    from datetime import datetime

    from aioredgif.models import JobRequest, JobState, JobStatus

    job = JobStatus(id="pending01", state=JobState.running, request=JobRequest(ids=["x"]), created=datetime.now())
    tc.app.state.jobs.jobs[job.id] = job
    assert tc.get("/v1/jobs/pending01/metadata").status_code == 409


def test_inline_playback_supports_range(api):
    tc, *_ = api
    r = tc.post("/v1/jobs", json={"urls": ["https://www.redgifs.com/users/paul57ak57"], "limit_per_source": 1})
    st = wait_for_job(tc, r.json()["id"])
    url = f"/v1/jobs/{st['id']}/files/{st['items'][0]['id']}?inline=true"
    full = tc.get(url)
    assert full.headers["content-type"] == "video/mp4"
    assert full.headers["content-disposition"].startswith("inline")
    part = tc.get(url, headers={"Range": "bytes=100-199"})
    assert part.status_code == 206 and len(part.content) == 100
    assert part.headers["content-range"] == "bytes 100-199/1000"


def test_faves_roundtrip(api):
    tc, _, tmp = api
    client_headers = {"X-Client-Id": "testclient123"}
    r = tc.post("/v1/jobs", json={"urls": ["https://www.redgifs.com/niches/lost-bet-captions"]})
    st = wait_for_job(tc, r.json()["id"])
    gid = st["items"][0]["id"]
    tc.get(f"/v1/jobs/{st['id']}/thumbs/{gid}")  # caches the thumbnail
    assert tc.get("/v1/faves").status_code == 400  # client id required
    fav = tc.put(f"/v1/faves/{gid}", json={"job_id": st["id"]}, headers=client_headers).json()
    assert fav["id"] == gid and "path" not in fav and fav["tags"]
    assert tc.put("/v1/faves/nope", json={"job_id": st["id"]}, headers=client_headers).status_code == 404
    items = tc.get("/v1/faves", headers=client_headers).json()["items"]
    assert [i["id"] for i in items] == [gid]
    play = tc.get(items[0]["play"], headers={"Range": "bytes=0-9"})
    assert play.status_code == 206 and len(play.content) == 10
    assert tc.get(items[0]["thumb"]).status_code == 200
    assert tc.get("/v1/faves", headers={"X-Client-Id": "someoneelse99"}).json()["items"] == []  # per browser
    assert tc.delete(f"/v1/faves/{gid}", headers=client_headers).status_code == 204
    assert tc.get("/v1/faves", headers=client_headers).json()["items"] == []
    assert tc.get("/v1/faves", headers={"X-Client-Id": "../../etc"}).status_code == 400


def test_same_link_is_not_downloaded_twice(api):
    tc, calls, tmp = api
    url = {"urls": ["https://www.redgifs.com/niches/lost-bet-captions"]}
    first = wait_for_job(tc, tc.post("/v1/jobs", json=url).json()["id"])
    media_after_first = sum(1 for c in calls if c.endswith(".mp4"))
    assert first["downloaded"] == 4 and first["already_had"] == 0
    r = tc.post("/v1/jobs", json=url)
    assert r.json()["id"] == first["id"] and r.json()["reused"] is True  # same history entry
    second = wait_for_job(tc, first["id"])
    assert second["already_had"] == 4 and second["downloaded"] == 4 and second["runs"] == 2
    assert sum(1 for c in calls if c.endswith(".mp4")) == media_after_first  # nothing fetched again
    # a different link that shares clips reuses them from the library too
    other = wait_for_job(tc, tc.post("/v1/jobs", json={"ids": ["nicheaclip", "nichebclip"]}).json()["id"])
    assert other["already_had"] == 2


def test_interrupted_pull_resumes_after_restart(api):
    tc, calls, tmp = api
    from datetime import datetime

    from aioredgif.downloader import JobManager, source_key
    from aioredgif.models import JobRequest, JobState, JobStatus

    s = tc.app.state.settings
    req = JobRequest(urls=["https://www.redgifs.com/users/paul57ak57"], limit_per_source=3)
    key, label = source_key(req)
    job = JobStatus(
        id="halfdone0001", state=JobState.running, request=req, created=datetime.now(), source_key=key, label=label
    )
    mgr = tc.app.state.jobs
    mgr.save(job)  # what was on disk when the server died
    part = tmp / "library" / "paul57ak57" / "gif1a.mp4.part"
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes((bytes(range(256)) * 4)[:400])  # 400 of 1024 bytes made it before the crash

    fresh = JobManager(mgr.client, s, mgr.library)  # "next session"
    assert fresh.jobs["halfdone0001"].state == JobState.interrupted
    tc.app.state.jobs = fresh
    hist = tc.get("/v1/history").json()["items"]
    assert hist[0]["id"] == "halfdone0001" and hist[0]["state"] == "interrupted"
    assert tc.portal.call(fresh.resume_interrupted) == ["halfdone0001"]
    st = wait_for_job(tc, "halfdone0001")
    assert st["state"] == "done" and st["downloaded"] == 3
    done = tmp / "library" / "paul57ak57" / "gif1a.mp4"
    assert done.read_bytes() == bytes(range(256)) * 4 and not part.exists()  # continued, not restarted


def test_resume_endpoint_and_forget(api):
    tc, *_ = api
    jid = wait_for_job(
        tc,
        tc.post("/v1/jobs", json={"urls": ["https://www.redgifs.com/users/paul57ak57"], "limit_per_source": 2}).json()[
            "id"
        ],
    )["id"]
    r = tc.post(f"/v1/jobs/{jid}/resume")
    assert r.status_code == 202
    st = wait_for_job(tc, jid)
    assert st["already_had"] == 2 and st["runs"] == 2
    assert tc.delete(f"/v1/history/{jid}").status_code == 204
    assert all(h["id"] != jid for h in tc.get("/v1/history").json()["items"])


def test_rewards_ranks_and_badges(api):
    tc, _, tmp = api
    from aioredgif.rewards import rank_for

    client_headers = {"X-Client-Id": "gooner0001"}
    assert tc.get("/v1/me", headers=client_headers).json()["rank"]["title"] == "Lurker"
    r = tc.post(
        "/v1/me/events",
        headers=client_headers,
        json={
            "seconds": 9999,
            "clips": ["a", "b"],
            "cave_opened": True,
            "cave_screens": 9,
            "edge_holds": 1,
            "faves": 1,
        },
    ).json()
    assert r["stats"]["seconds"] == 30  # capped per report
    assert {b["id"] for b in r["new_badges"]} == {"into_cave", "full_wall", "held_it", "got_one"}
    again = tc.post("/v1/me/events", headers=client_headers, json={"seconds": 5, "clips": ["a"]}).json()
    assert again["new_badges"] == [] and again["stats"]["clips_seen"] == 2  # distinct clips
    ups = []
    for _ in range(29):  # 30 + 5 + 29*30 = 905 s
        last = tc.post("/v1/me/events", headers=client_headers, json={"seconds": 30}).json()
        ups += [last["rank_up"]["title"]] if last["rank_up"] else []
    assert last["stats"]["seconds"] == 905 and last["rank"]["title"] == "Initiate" and ups == ["Initiate"]
    assert rank_for(3600)["title"] == "Locked In" and rank_for(100 * 3600)["next_title"] is None
    assert tc.post("/v1/me/events", headers=client_headers, json=["x"]).status_code == 400
    assert tc.get("/v1/me", headers={"X-Client-Id": "otherbrowser1"}).json()["stats"]["seconds"] == 0


def test_library_browse_filter_play_zip(api):
    import io
    import zipfile

    tc, *_ = api
    wait_for_job(
        tc, tc.post("/v1/jobs", json={"urls": ["https://www.redgifs.com/niches/lost-bet-captions"]}).json()["id"]
    )
    wait_for_job(
        tc,
        tc.post("/v1/jobs", json={"urls": ["https://www.redgifs.com/users/paul57ak57"], "limit_per_source": 2}).json()[
            "id"
        ],
    )
    lib = tc.get("/v1/library").json()
    assert lib["total"] == 6
    assert {c["creator"] for c in lib["creators"]} == {"maker0", "maker1", "paul57ak57"}
    assert lib["tags"][0] == {"tag": "Blonde", "count": 4}
    solo = tc.get("/v1/library", params={"tag": "solo"}).json()
    assert solo["total"] == 3 and all("Solo" in i["tags"] for i in solo["items"])  # 2 niche + 1 creator post
    assert tc.get("/v1/library", params={"creator": "maker1"}).json()["total"] == 2
    assert tc.get("/v1/library", params={"q": "blonde"}).json()["total"] >= 1
    assert tc.get("/v1/library", params={"sort": "random", "limit": 2}).json()["items"].__len__() == 2
    item = lib["items"][0]
    part = tc.get(item["play"], headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100
    assert tc.get(item["thumb"]).status_code == 200
    z = tc.get("/v1/library/archive", params={"creator": "maker0"})
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert len([n for n in names if n.endswith(".mp4")]) == 2 and all(n.startswith("maker0/") for n in names)
    assert tc.get("/v1/library/archive", params={"tag": "nothing-here"}).status_code == 404
    # library clips can be faved without a job
    client_headers = {"X-Client-Id": "libraryfan01"}
    assert tc.put(f"/v1/faves/{item['id']}", headers=client_headers, json={}).status_code == 200
    assert tc.get("/v1/faves", headers=client_headers).json()["items"][0]["id"] == item["id"]


def test_bad_sort_order_falls_back_and_is_remembered(api):
    """Real RedGIFs answered: 400 Bad sorting order "trending", must be one of: trending, oldest, latest, best, hot."""
    tc, calls, _ = api
    client = tc.app.state.client
    seen = []
    orig = client._http.get

    async def fake_get(url, params=None, **kw):
        if "/v2/niches/" in str(url) and str(url).endswith("/gifs"):
            seen.append((params or {}).get("order"))
            if (params or {}).get("order") in ("trending", "hot"):
                return httpx.Response(
                    400,
                    json={
                        "error": {
                            "message": BAD_SORT_MESSAGE,
                        }
                    },
                    request=httpx.Request("GET", "https://api.redgifs.com" + str(url)),
                )
        return await orig(url, params=params, **kw)

    client._http.get = fake_get
    st = wait_for_job(
        tc, tc.post("/v1/jobs", json={"urls": ["https://www.redgifs.com/niches/lost-bet-captions"]}).json()["id"]
    )
    assert st["state"] == "done" and st["downloaded"] == 4, st
    assert seen[:3] == ["trending", "hot", None]  # nearest equivalent, then the server default
    seen.clear()
    assert tc.get("/v1/niches/lost-bet-captions/gifs").status_code == 200
    assert seen == [None]  # remembered: no more failed attempts
