# Changelog

## 1.0.0 (2026-11-20)

First release as **aioredgif**.

### Added
- Goon cave **Clips: Show whole** (new default): every clip is shown edge to edge with nothing cut off
  or drawn over it; leftover space shows a blurred poster. Screens are shaped more tightly to their
  clips in this mode. **Fill screen** keeps the old cover behaviour.
- Command line for developers: `aioredgif pull | resume | info | export | library | history | serve`,
  with the RG logo in ASCII, live progress bars (count, percent, speed, ETA), Ctrl+C to pause a pull,
  `--json` on every command, and plain output for pipes and `NO_COLOR`.
- Creator reports (`aioredgif.creator/1`): profile and profile image, clip and image counts, footage,
  views, likes and like rate, every tag with first and last use, tag pairs, niches, upload timeline by
  month, weekday and hour, most viewed and liked posts, and download links per post.
  `GET /v1/users/{name}/report`, `GET /v1/library/creators`, `aioredgif info`.
- Library exports as JSON, JSON Lines or CSV (`GET /v1/library/export`, `aioredgif export`).
- Data guide (`docs/DATA.md`) and command line guide (`docs/CLI.md`).
- Install from GitHub with pip (`pip install "aioredgif @ git+https://github.com/ahamlabs/aioredgif.git"`).
- Goon cave "Fit to clips" layout: screens shaped like their clips, packed to fill the whole wall
  evenly, re-fitted on resize and rotation; clips that would be cropped heavily are shown whole over a
  blurred poster. Any number of screens from 1 to 9; the equal grid stays as an option. Touch
  double-tap, and a folding settings bar on phones and short screens.
- Include / exclude tag filters: when pulling (`include_tags`, `exclude_tags`, `tag_match`; skipped
  posts are never downloaded), on the results and in the Library (tap a chip to keep, hide or clear;
  match any or all), carried through to the player, cave and zip downloads
  (`/v1/library?include=&exclude=&match=`).
- Pause and resume pulls (`POST /v1/jobs/{id}/pause`), and start other pulls while one runs.
- Images in the goon cave: show clips, images or both.
- Library picks up files copied in by hand at any depth, re-scans by itself, and has a Rescan button
  (`POST /v1/library/rescan`). Clips without a poster show a frame of the video.
- Downloads and pulls from earlier versions are imported into the library and History.
- RG artwork as logo, favicon, app icons and hero art; web app manifest.
- User guide, API reference and developer guide.

### Changed
- Cave screens lost their border, and the active-screen ring and rotation bar moved into the gap
  between screens, so they no longer cover the edges of a clip.
- Package renamed from `app` to `aioredgif`; run it with `aioredgif` or `python -m aioredgif`.
- Settings use the `AIOREDGIF_` prefix (was `RG_`).
- Code split into an app factory and one router per area; Google-style docstrings throughout; ruff for
  PEP 8 linting and formatting.
- The web page is split into HTML, CSS and JS files. Browser settings move from `reel.*` to
  `aioredgif.*` keys automatically, so faves and ranks carry over.

### Fixed
- The header overflowed sideways on phones, hiding the Goon cave button.
- Previously downloaded videos did not appear in the library if they were pasted in while the server
  ran, sat deeper than `library/<creator>/`, or came from the old per-pull folders.
- Resuming a pull from History could show another pull's progress.

## 0.x

Development versions: API client, downloader, web app, player, library, history, faves, rewards,
goon cave, edge timer, sort-order fallback.
