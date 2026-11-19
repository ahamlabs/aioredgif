# Command line

Installing aioredgif gives you the `aioredgif` command (`python -m aioredgif` works too). With no
command it starts the web app. Every other command works directly on the download folder, without the
web server. You can run both at once on the same folder.

```text
    ____  ______
   / __ \/ ____/
  / /_/ / / __      aioredgif 1.0.0
 / _, _/ /_/ /      pull. keep. play.
/_/ |_|\____/       adults only
```

Messages and progress go to stderr, while data (`--json`, exports) goes to stdout. That means
`aioredgif info @name --json > name.json` writes clean JSON while you still see the progress bar.
Colour switches off by itself when output is not a terminal or `NO_COLOR` is set.

## Options every command takes

| Option | Meaning |
|---|---|
| `--download-dir PATH` | The download folder (default: `AIOREDGIF_DOWNLOAD_DIR`, else `downloads`) |
| `--no-color` | Plain text |
| `--ascii` | Draw bars with `#` and `-` |
| `-q`, `--quiet` | No banner or progress, only results |
| `-v`, `--verbose` | Log every request to RedGIFs |

## `aioredgif pull SOURCE...`

Downloads into the library, exactly like the web app, and with the same dedupe: anything you already
have is reused.

Sources can be any mix of:

- RedGIFs links (creator, niche, tag search or watch page)
- `@creator` or a bare handle
- `#tag`
- `niche:slug`

| Option | Meaning |
|---|---|
| `--limit N` | Most posts per source (default 100) |
| `--quality hd\|sd` | File quality (default hd) |
| `--no-images` | Skip image posts |
| `--include a,b` / `--exclude c` / `--match any\|all` | Tag filters; excluded posts are never downloaded |
| `--zip PATH` | Also write the files, sidecars, `metadata.json` and `tags.json` to a .zip |
| `--json` | Print the finished pull (JobStatus) on stdout |

```text
pulling  [██████████░░░░░░░░░░░░░░░░░░░░]  41/120   34%  6.2 MB/s  eta 1:48  gif-id
```

Press **Ctrl+C** to pause. Finished files stay, a half-finished file continues from the same byte
later, and the command prints how to resume.

```bash
aioredgif pull https://www.redgifs.com/users/someone --exclude pov --zip someone.zip
aioredgif pull niche:lost-bet-captions "#blonde" --limit 50 --include solo
```

## `aioredgif resume PULL-ID`

Carries on with a paused, interrupted or failed pull. `aioredgif history` lists the ids. Takes `--zip`
and `--json`.

## `aioredgif info CREATOR`

Reads a creator from RedGIFs and prints their profile (with profile image link), counts of clips and
images, footage, views, likes and like rate, upload dates, top tags as a bar chart, uploads by month,
and the most viewed posts. Nothing is downloaded.

| Option | Meaning |
|---|---|
| `--limit N` | Most posts to read (default 1000) |
| `--json` | The full report on stdout (schema in [DATA.md](DATA.md)) |
| `--out PATH` | Write the full report to a file and show the summary |
| `--no-posts` | Leave the per-post list out of the JSON |

## `aioredgif export`

Your library as data, without touching RedGIFs.

| Option | Meaning |
|---|---|
| `--format json\|jsonl\|csv` | Output format (default jsonl) |
| `--creator NAME`, `--kind all\|video\|image` | Narrow it down |
| `--include` / `--exclude` / `--match` | Tag filters |
| `--creators` | One creator report per creator instead of one record per post |
| `--out PATH` | Write to a file instead of stdout |

```bash
aioredgif export --format csv --out library.csv
aioredgif export --format jsonl | jq -r 'select(.views > 10000) | .page_url'
python -c "import pandas as pd; print(pd.read_json('library.jsonl', lines=True).groupby('creator').size())"
```

## `aioredgif library` and `aioredgif history`

`library` summarises what is stored (items, size, footage, creators and tags), with `--creator` and
the tag filters. `history` lists every pull, newest first. Both take `--json`.

## `aioredgif serve`

The web app and API. `--host`, `--port` and `--reload` (for development). `aioredgif --port 9000`
works too.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Done, or paused on request |
| 1 | The pull failed or the creator could not be read |
| 2 | Bad input, such as an unknown pull id |
| 130 | Stopped with Ctrl+C where pausing was not possible |

## Using it from scripts

Everything the CLI does is also available from Python:

```python
import asyncio
from aioredgif.config import Settings
from aioredgif.creators import creator_report
from aioredgif.services import open_services

async def main():
    async with open_services(Settings(browser_enabled=False)) as services:
        report = await creator_report(services.client, "someone", limit=200, library=services.library)
        print(report["summary"]["tags"][:5])

asyncio.run(main())
```
