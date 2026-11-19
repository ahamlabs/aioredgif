# Developing aioredgif

## Set up

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium        # only for the browser fallback
aioredgif --reload                 # restarts on code changes
```

## Checks

```bash
pytest                 # the full suite; no network needed
ruff check .           # lint: PEP 8, imports, bugbear, Google-style docstrings
ruff format .          # formatting
```

CI (`.github/workflows/ci.yml`) runs all three on every push. Keep them green.

## How it fits together

```
browser ──HTTP──> api/* routers ──> services on app.state ──> RedGIFs / disk
```

`app.create_app(settings, transport)` builds the app. On startup it creates one of each service and
puts it on `app.state`; routers reach them through `request.app.state` (see `api/deps.py`).

| Service | Module | Job |
|---|---|---|
| `client` | `client.py` | Talks to RedGIFs: token, throttle, retries, sort-order fallback, media streams |
| `library` | `library.py` | Indexes every media file under the download folder; metadata for browsing |
| `jobs` | `downloader.py` | Runs pulls; saves, pauses, resumes and dedupes them; imports older versions |
| `thumbs` | `thumbs.py` | Fetches and caches thumbnails |
| `faves` | `faves.py` | Faves per client id |
| `profiles` | `rewards.py` | Ranks and badges per client id |
| `browser` | `browser.py` | Optional Playwright fallback |
| `rate_buckets` | `ratelimit.py` | Free-tier limits |

`tagfilter.py` holds the include/exclude rule (`TagFilter`) shared by pulls (`JobRequest.tag_filter`)
and the library (`Library.search(tags=...)`). The page has the same rule in JavaScript (`TagPick` in
`aioredgif.js`); keep the two in step.

`services.open_services(settings, transport)` creates `client`, `library`, `jobs` and `thumbs` and closes
them cleanly; both the web app's lifespan and the command line (`cli.py`) use it, so a pull started
from the terminal behaves exactly like one started from the page. `creators.py` builds creator
reports and `exports.py` renders library exports; both are plain functions over post records, so they
work on live RedGIFs data and on sidecars alike.

### A pull, step by step

1. `POST /v1/jobs` → `JobManager.submit`. `source_key()` turns the request into a stable key; if a
   pull with that key exists it is re-run instead of creating a new one.
2. `_run` collects posts (`client.iter_user / iter_niche / iter_search / gifs_by_ids`), saving the job
   to `.jobs/<id>.json` as it goes.
3. For each post, `_fetch` takes a per-id lock, checks the library, and only calls `download_one` if
   the file is missing. `download_one` continues a `.part` file with a Range request.
4. A sidecar is written next to each file, and `metadata.json` / `tags.json` at the end.
5. Cancelling the task (pause or shutdown) leaves `.part` files in place; the job is saved as
   `paused` or `interrupted`.

### Storage

All state is plain files under `download_dir`, written atomically (write `.part`, then rename):
`library/`, `<job>/`, `.jobs/`, `.faves/`, `.profiles/`, `.thumbs/`. That keeps the server easy to back
up and inspect, but it is one process only. To run several workers, move jobs to a shared queue
(Redis with RQ or Arq) and the stores to a database; the service interfaces stay the same.

### The web app

`aioredgif/static/` is plain HTML, CSS and JavaScript with no build step:

- `index.html`: markup for the hero, results, library, history, rewards, player and cave.
- `css/aioredgif.css`: colours and type are defined once in `:root`.
- `js/layout.js`: the cave's layout maths, with no page dependencies (also loads in Node for tests).
  It packs boxes by recursive side-by-side / stacked cuts and caches results by the set of clip shapes.
- `js/aioredgif.js`: one script in sections (pulling, results, player, faves, session and edge timer,
  cave, views). It only talks to the API documented in `API.md`.
- `img/`: the RG logo, icons and artwork. Replace them to rebrand; keep the file names.

## Tests

`tests/conftest.py` builds an app with a fake RedGIFs (`httpx.MockTransport`) and a temporary download
folder per test. The fake serves creators, niches, tag search, ids, thumbnails and Range-capable media,
and can be made to fail (429, bad sort order). `wait_for_job()` polls a pull until it settles.

When you add a feature, add a test next to similar ones:

- `test_api.py`: lookups, pulls, dedupe, resume, metadata, faves, rewards, the page itself.
- `test_library_and_pause.py`: pausing, the library index, importing older downloads.
- `test_layout_js.py`: the cave layout, run with Node when it is installed (skipped otherwise).
- `test_tag_filters.py`: the include/exclude rule, filtered pulls, filtered library.
- `test_parsing.py`: links and saved pages (fixtures are real saved RedGIFs pages).

## Adding an endpoint

1. Put it in the router for its area under `aioredgif/api/` (or add a router and include it in
   `app.py`).
2. Give it a Google-style docstring; the first line becomes its summary in `/docs`.
3. Reach services through `request.app.state` or the helpers in `api/deps.py`.
4. Document it in `docs/API.md` and add a test.

## Style

- PEP 8 via ruff, 120 columns, Google-style docstrings on every public module, class and function.
- Names say what things are (`job`, `entry`, `gif_id`), not `j`, `e`, `g`.
- Comments explain why, not what.
- Errors users can see are plain sentences that say what to do next.

## Releasing

1. Update `__version__` in `aioredgif/__init__.py` and `version` in `pyproject.toml`.
2. Add an entry to `CHANGELOG.md`.
3. `pytest && ruff check . && ruff format --check .`
4. `python -m build` to make the wheel and sdist, and check `pip install dist/*.whl` runs
   `aioredgif version`.
5. Tag the release (`git tag v1.0.0 && git push --tags`). Users install a tag with
   `pip install "aioredgif @ git+https://github.com/OWNER/aioredgif.git@v1.0.0"`.
