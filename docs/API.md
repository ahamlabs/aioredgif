# aioredgif API reference

Everything the web app does goes through this HTTP API, so you can script it, build your own front
end, or plug aioredgif into something else. Interactive docs with "try it out" buttons are served at
`/docs` (Swagger) and `/redoc`; the raw schema is at `/openapi.json`.

Base URL in the examples: `http://127.0.0.1:8000`.

- [Conventions](#conventions)
- [Quick recipes](#quick-recipes)
- [RedGIFs lookups](#redgifs-lookups)
- [Pulls](#pulls)
- [Library](#library)
- [Faves](#faves)
- [Rewards](#rewards)
- [Site](#site)
- [Data shapes](#data-shapes)

## Conventions

**Limits.** Clients without an API key are limited to `AIOREDGIF_FREE_RPM` requests per minute
(per IP) on lookup and pull endpoints, and to `AIOREDGIF_FREE_MAX_ITEMS_PER_JOB` clips per pull. Send
`X-API-Key: <key>` with a key from `AIOREDGIF_API_KEYS` to skip both. Over the limit you get
`429` with a `Retry-After` header.

**Client id.** Faves and rewards belong to a browser or app, identified by a random id of 8 to 64
letters, digits, `_` or `-`. Send it as `X-Client-Id: <id>`, or as `?c=<id>` where headers are not
possible (for example `<video src>`). Make one up once and keep it.

**Errors.** Errors are JSON: `{"detail": "..."}`.

| Status | Meaning |
|---|---|
| 400 | Bad input (not a RedGIFs link, bad client id, RedGIFs refused the request) |
| 404 | Not found (post, pull, file, fave) |
| 409 | Wrong state (pausing a pull that isn't running, metadata before a pull finishes) |
| 429 | Rate limited (yours, or RedGIFs') |
| 502 | RedGIFs failed or returned something unusable |

**Media.** Every file endpoint supports HTTP Range requests, so players can seek. File endpoints play
inline by default where noted; add `download=true` (or omit `inline=true` on pull files) to get an
attachment.

## Quick recipes

Pull a creator and wait for it:

```bash
JOB=$(curl -s -X POST localhost:8000/v1/jobs -H 'content-type: application/json' \
  -d '{"urls": ["https://www.redgifs.com/users/paul57ak57"], "limit_per_source": 50}' | jq -r .id)

until [ "$(curl -s localhost:8000/v1/jobs/$JOB | jq -r .state)" != "running" ]; do sleep 2; done
curl -s localhost:8000/v1/jobs/$JOB | jq '{state, discovered, downloaded, already_had, failed}'
```

Download it all as a zip, with metadata:

```bash
curl -o stash.zip localhost:8000/v1/jobs/$JOB/archive
```

Pause it, then resume:

```bash
curl -X POST localhost:8000/v1/jobs/$JOB/pause
curl -X POST localhost:8000/v1/jobs/$JOB/resume
```

Find every clip in your library tagged "solo" by one creator, and zip them:

```bash
curl -s 'localhost:8000/v1/library?creator=maker0&tag=solo' | jq '.items[] | {id, tags, play}'
curl -o solo.zip 'localhost:8000/v1/library/archive?creator=maker0&tag=solo'
```

The same from Python:

```python
import time
import httpx

api = httpx.Client(base_url="http://127.0.0.1:8000")
job = api.post("/v1/jobs", json={"urls": ["https://www.redgifs.com/niches/lost-bet-captions"]}).json()
while (status := api.get(f"/v1/jobs/{job['id']}").json())["state"] in ("queued", "running"):
    time.sleep(2)
print(status["downloaded"], "clips;", status["already_had"], "were already in the library")

tags = api.get(f"/v1/jobs/{job['id']}/stats").json()["tags"]
print("top tags:", [(t["tag"], t["count"]) for t in tags[:5]])
```

## RedGIFs lookups

Read-only calls that go straight to RedGIFs. Nothing is stored. All are rate limited.

### `GET /v1/gifs/{id}`
One post: creator, tags, size, stats and media URLs (`urls.hd`, `urls.sd`, `urls.thumbnail`...).

### `GET /v1/gifs/{id}/download?quality=hd|sd`
Streams the post's file to you without storing it.

### `GET /v1/users/{username}/gifs?page=1&count=40&order=new`
One page of a creator's posts (`count` up to 80). Returns a [Page](#page).

### `GET /v1/users/{username}/report?limit=200&posts=true`
A full creator report: profile (handle, display name, profile image, followers, views, join date),
summary statistics (clips and images, footage, views and likes, top tags with first and last use, tag
pairs, niches, upload timeline by month, weekday and hour) and every post with its download links.
`limit` is the most posts to read (up to 2000); `posts=false` returns only the profile and summary.
Unknown creators return `404`. Schema `aioredgif.creator/1`, described field by field in
[DATA.md](DATA.md).

### `GET /v1/search?tags=a,b&page=1&count=40&order=trending`
Posts carrying all the given tags.

### `GET /v1/niches/{niche}` and `GET /v1/niches/{niche}/gifs`
A niche's details, and one page of its feed.

`order` accepts `new`, `latest`, `top`, `best`, `trending`, `hot` and `oldest`. RedGIFs does not
accept every word on every feed; when it refuses one, aioredgif falls back to the nearest equivalent or
the feed's default and remembers what worked.

### `POST /v1/resolve`
Body `{"url": "...", "use_browser": false}`. Works out what any RedGIFs link points at and returns
`kind` (`watch`, `creator`, `niche`, `tag`), the post ids, and for watch links the media URLs. With
`use_browser: true` (needs Playwright) it reads the page like a browser would.

## Pulls

A pull ("job") collects posts from one or more sources and downloads them into the library.

### `POST /v1/jobs`
Start a pull. Body (all fields optional, but give at least one source):

```json
{
  "urls": ["https://www.redgifs.com/users/paul57ak57"],
  "users": ["somecreator"],
  "niches": ["lost-bet-captions"],
  "tags": ["blonde", "solo"],
  "ids": ["mysteriousspottedzethusspinipes"],
  "limit_per_source": 100,
  "order": "new",
  "quality": "hd",
  "include_images": true,
  "include_tags": ["blonde", "solo"],
  "exclude_tags": "pov, captions",
  "tag_match": "any"
}
```

**Tag filter.** `include_tags` and `exclude_tags` take a list or comma separated text. A post is
kept if it has none of `exclude_tags` and, when `include_tags` is given, any of them (`tag_match:
"any"`) or all of them (`"all"`). Exclusion wins; case and a leading `#` are ignored. Filtered posts
are never downloaded and are counted in `filtered_out`. The same sources with a different filter are a
separate history entry.

Returns `202` with a [JobStatus](#jobstatus). If the same sources were pulled before (same quality and
image setting), you get that same pull back with `"reused": true`; it runs again and only fetches
clips that are not in the library. `already_had` counts the reused ones.

### `GET /v1/jobs/{id}`
Progress and results. Poll every second or two while `state` is `queued` or `running`.

States: `queued`, `running`, `done`, `failed`, `paused` (you stopped it), `interrupted` (the server
stopped mid-pull; it resumes on the next start).

### `POST /v1/jobs/{id}/pause`
Stop a running pull. Returns `409` if it is not running. Finished clips stay; a half-downloaded file
continues from the same byte when resumed.

### `POST /v1/jobs/{id}/resume`
Continue a paused, interrupted or failed pull, or fetch new clips for a finished one.

### `GET /v1/history?limit=100`
Every pull, newest first, as light summaries (`id`, `label`, `urls`, `state`, counts, `runs`,
`last_run`, `imported`, `tag_filter` (e.g. `"only blonde or solo, not pov"`), `filtered_out`, up to four
thumbnail URLs).

### `DELETE /v1/history/{id}`
Remove a pull from history (`409` while it runs). Its clips stay in the library.

### `GET /v1/jobs`
Every pull with full detail.

### `GET /v1/jobs/{id}/files/{gif_id}?inline=true`
One finished file. `inline=true` plays it in a browser; without it you get an attachment.

### `GET /v1/jobs/{id}/archive`
Everything the pull has stashed so far, plus sidecars, `metadata.json` and `tags.json`, as one .zip.

### `GET /v1/jobs/{id}/stats`
Live tag, niche and creator counts and the 25 most common tag pairs. Works while the pull runs.

### `GET /v1/jobs/{id}/metadata?kind=all|tags`
`metadata.json` (`all`) or `tags.json` (`tags`). `409` until the pull finishes.

### `GET /v1/jobs/{id}/thumbs/{gif_id}`
A post's thumbnail, fetched once through the server and cached.

## Library

Every file the server has: everything pulled, files from older versions, and files copied into the
download folder by hand.

### `GET /v1/library`

| Parameter | Default | Meaning |
|---|---|---|
| `q` | | Text matched against id, creator, tags and niches |
| `creator` | | Exact creator handle |
| `include` | | Comma separated tags to keep |
| `exclude` | | Comma separated tags to drop (wins over `include`) |
| `match` | `any` | `any` or `all` of the `include` tags |
| `tag` | | A single tag the item must have (older form of `include`) |
| `kind` | `all` | `all`, `video` or `image` |
| `sort` | `stashed` | `stashed` (newest first), `random`, `longest`, `shortest`, `views`, `creator` |
| `offset`, `limit` | `0`, `120` | Paging (`limit` up to 1000) |

Returns `total`, `clips`, `images`, `total_bytes`, `total_duration_s`, `creators` (with counts),
`tags` (top 60, with counts) and `items`. Each item has `id`, `creator`, `tags`, `niches`,
`duration_s`, `width`, `height`, `views`, `likes`, `created`, `bytes`, `stashed`, `image`, and the URLs
`play`, `dl` and `thumb`.

### `POST /v1/library/rescan`
Look for new files on disk now. Returns `{"indexed": <count>}`. (It also happens by itself every
`AIOREDGIF_LIBRARY_RESCAN_SECONDS`.)

### `GET /v1/library/archive`
A .zip of everything matching the same filters as browsing (`q`, `creator`, `include`, `exclude`,
`match`, `kind`), with sidecars.

```bash
# every clip tagged blonde or solo, but not pov
curl -o picks.zip 'localhost:8000/v1/library/archive?include=blonde,solo&exclude=pov'
```

### `GET /v1/library/export?format=jsonl`
Every matching library item as a post record. `format` is `json`, `jsonl` (default) or `csv`; takes
the browsing filters `q`, `creator`, `include`, `exclude`, `match` and `kind`. Newest upload first.

```bash
curl 'localhost:8000/v1/library/export?format=csv&exclude=pov' -o library.csv
```

### `GET /v1/library/creators?posts=false`
A creator report (`aioredgif.creator/1`, `source: "library"`) for every creator in the library, built
from sidecars without asking RedGIFs. `posts=true` includes each post.

### `GET /v1/library/{id}/file?download=false`
Play (default) or download one item.

### `GET /v1/library/{id}/thumb`
Its thumbnail. Images are their own thumbnail. Clips without a known poster return `404`; the web app
then shows a frame of the clip.

## Faves

All fave endpoints need the [client id](#conventions).

| Method | Path | Does |
|---|---|---|
| `GET` | `/v1/faves` | Your faves, newest first, each with `play`, `dl` and `thumb` URLs |
| `PUT` | `/v1/faves/{id}` | Fave any item in the library (optional body `{"job_id": "..."}`) |
| `DELETE` | `/v1/faves/{id}` | Un-fave (the file stays) |
| `GET` | `/v1/faves/{id}/file?c=<client-id>` | Play, or `download=true` to save |
| `GET` | `/v1/faves/{id}/thumb?c=<client-id>` | Thumbnail |

## Rewards

### `GET /v1/me`
Your `rank` (`title`, `level`, `seconds`, `next_title`, `next_at`, `progress`), the rank ladder,
`stats` (`seconds`, `stashed`, `faves`, `caves`, `max_screens`, `edge_holds`, `tag_filters`,
`clips_seen`) and every badge with `earned` (timestamp or null) and `progress` (0 to 1).

### `POST /v1/me/events`
Credit activity. The web app sends one every 15 seconds:

```json
{"seconds": 15, "clips": ["id1", "id2"], "edge_holds": 1, "stashed": 0,
 "cave_opened": false, "cave_screens": 4, "tag_filter": false, "faves": 3}
```

`seconds` is capped at 30 per call and only time spent actually playing should be sent. The answer
is `/v1/me` plus `new_badges` (list) and `rank_up` (the new rank, or null).

## Site

| Method | Path | Does |
|---|---|---|
| `GET` | `/health` | `{"ok": true, "version": "1.0.0"}` |
| `GET` | `/v1/brand` | Images in `aioredgif/static/brand/`, used by the hero |

## Data shapes

### JobStatus

```json
{
  "id": "6bb87f781a67",
  "state": "running",
  "request": {"urls": ["..."], "limit_per_source": 100, "quality": "hd", "...": "..."},
  "discovered": 18,
  "downloaded": 9,
  "already_had": 4,
  "filtered_out": 3,
  "failed": 0,
  "items": [{"id": "...", "user_name": "...", "tags": ["..."], "niches": ["..."], "sources": ["niche:..."]}],
  "files": [{"id": "...", "path": "...", "bytes": 1048576, "skipped": false, "error": null}],
  "error": null,
  "created": "2026-11-20T21:04:11",
  "last_run": "2026-11-20T21:04:11",
  "finished": null,
  "label": "niche:lost-bet-captions",
  "runs": 1,
  "reused": false,
  "imported": false
}
```

### Page

`{"items": [Gif, ...], "page": 1, "pages": 3, "total": 214}`

### Sidecar (`library/<creator>/<id>.json`)

`id`, `page_url`, `creator`, `creator_url`, `tags`, `niches`, `description`, `found_via`, `type`,
`duration_s`, `width`, `height`, `has_audio`, `views`, `likes`, `verified`, `created`, `media` (URLs),
`file` (relative to the download folder), `bytes`, `status` (`saved`, `skipped` or `failed`), `error`,
and `raw`, the full object RedGIFs returned.

### tags.json

```json
{
  "tags": {"Captions": {"count": 18, "share": 1.0, "items": [{"id": "...", "file": "library/..."}]}},
  "niches": {"lost-bet-captions": {"count": 18, "items": ["..."]}},
  "creators": {"creator0": 6},
  "tag_pairs": [{"tags": ["Blonde", "Captions"], "count": 7}]
}
```
