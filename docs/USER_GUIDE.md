# aioredgif user guide

This guide walks through the web app. Start the server (`aioredgif`), then open
http://127.0.0.1:8000/. Everything here is also available through the [API](API.md).

- [Pulling clips](#pulling-clips)
- [Tag filters](#tag-filters)
- [Pausing, resuming and running several pulls](#pausing-resuming-and-running-several-pulls)
- [History](#history)
- [The library](#the-library)
- [The player](#the-player)
- [The goon cave](#the-goon-cave)
- [Edge timer](#edge-timer)
- [Faves](#faves)
- [Rewards](#rewards)
- [Where your files and data are](#where-your-files-and-data-are)
- [Getting the information you need](#getting-the-information-you-need)
- [Bringing in files from elsewhere](#bringing-in-files-from-elsewhere)
- [Troubleshooting](#troubleshooting)

## Pulling clips

Paste a RedGIFs link into the box at the top and press **Load it all**. These links work:

| Link | Pulls |
|---|---|
| `redgifs.com/users/<name>` | A creator's posts |
| `redgifs.com/niches/<slug>` | A niche's feed |
| `redgifs.com/gifs/<tag>` | Posts with that tag |
| `redgifs.com/watch/<id>` | One post |

Use the handle in the link, not the display name on the profile. For example, the profile shown as
"JuliaBNWO" is `redgifs.com/users/paul57ak57`.

Before pulling you can choose:

- **HD or SD**: file quality.
- **Up to**: how many posts to take (25, 100, 250, or everything up to 1,000). Free-tier servers cap
  this at 100 per pull unless you have an API key.
- **Discreet mode**: blurs every preview until you hover over it or play it.

As clips arrive, each numbered frame changes from **LOADING** to **STASHED**. You can play any stashed
clip straight away, before the pull finishes.

**Download .zip** next to Load it all does the same pull and downloads everything as one .zip when it
is done. While a pull is running, the **Download .zip** button in the results gives you whatever is
stashed so far.

If you paste a link you have pulled before, aioredgif tells you so: clips already in your library are
reused and only new ones download.

## Tag filters

You can filter by tag in three places, and they all work the same way: a post is kept if it has none
of the tags you hide and, if you chose tags to keep, **any** of them (or **all** of them, if you
switch to "all"). Hiding always wins. Tags ignore case and a leading `#`.

**Before pulling.** Open **Tag filter** under the link box:

- **Only keep posts tagged**: e.g. `blonde, solo`.
- **Skip posts tagged**: e.g. `pov, captions`.
- **Keep a post if it has** any or all of the kept tags.

Skipped posts are never downloaded; the results say how many were skipped. The filter is remembered
for your next pull. The same link with a different filter is a separate entry in History.

**On the results and in the Library.** Tap a tag chip to cycle it:

| Tap | Chip | Means |
|---|---|---|
| once | pink with ✓ | keep only clips with this tag |
| twice | red, struck through, with ✕ | hide clips with this tag |
| three times | plain | no filter on this tag |

With two or more kept tags, an **Any of these / All of these** switch appears. **Clear tag filter**
resets everything. Hidden tags stay on screen so you can un-hide them. The player, **Start session**,
**Play these**, **Cave with these** and the Library's **Download .zip** all follow the filter.

## Pausing, resuming and running several pulls

- **Pause** (in the results, or in History) stops a pull. Everything stashed so far stays in your
  library, and a half-downloaded file is kept so it can continue later.
- **Resume** carries on from where it stopped. Nothing is downloaded twice.
- You can paste another link at any time, even while a pull is running. The earlier pull keeps going
  in the background; open it again from History.
- If the server is stopped mid-pull (closed, crashed, restarted), the pull is marked **interrupted**
  and resumes on its own the next time the server starts. Paused pulls stay paused until you resume them.

## History

**History** lists every pull, newest first, with how many clips it found and stashed, how many were
reused from the library, and when it last ran. For each pull you can:

- **Resume** a paused, interrupted or failed pull.
- **Pull new clips** for a finished one (fetches only what is new since last time).
- **Pause** one that is running.
- **Open** it to see its clips, tags and buttons again.
- **Download .zip** of its clips and metadata.
- **Forget** it. This removes it from History only; its clips stay in the library.

Pulls made by versions before 1.0 are added to History automatically, marked "From an older version".

## The library

**Library** shows every clip and image you have, from every pull and every session, including files
you copied in yourself.

- **Search** matches creators, tags, niches and file names.
- **Filter** by creator, by type (clips, images or both) or by tapping a tag.
- **Sort** by newest, random, longest, shortest, most viewed or creator.
- **Play these** opens the player on the filtered set; **Cave with these** puts it on the cave wall.
- **Download .zip** downloads exactly what you have filtered, with the JSON sidecars.
- **Rescan folder** looks for files you have just copied into the downloads folder. The library also
  does this by itself every 30 seconds.

Clips without a poster image (for example ones you copied in) show a frame of the video instead.

## The player

Tap any stashed clip, library item or fave to open the player. It plays at once, with sound.

| Control | Key |
|---|---|
| Play or pause (or tap the video) | Space |
| Seek 5 seconds | Left / Right |
| Volume | Up / Down |
| Mute | M |
| Edge loop: repeat this clip | L |
| Keep going: roll into the next clip | K |
| Shuffle | S |
| Fave | H |
| Cycle the edge timer | E |
| Next / previous | N / P |
| Fullscreen (or double-tap) | F |
| Close | Esc |

Speed runs from 0.5x to 2x. Volume, mute, loop, keep going, shuffle and speed are remembered by your
browser. If a tag filter is on, the player sticks to clips with that tag.

## The goon cave

**Goon cave** fills the screen with a wall of clips.

- **Screens**: 1 to 9.
- **Layout**: **Fit to clips** (the default) gives every screen a box shaped like its clip and packs
  them so the whole wall is filled, with screens of similar size and as little spare space as possible.
  Portrait, square and landscape clips can share one wall. It re-fits when you resize the window or
  turn your phone or tablet. **Equal grid** is the classic layout: same-size boxes.
- **Clips**: **Show whole** (the default) keeps every pixel of every clip in view. Where a screen's
  shape doesn't quite match its clip, the leftover strip shows a blurred copy of the poster. Nothing is
  drawn over the picture: the "sound on" ring and the rotation bar sit in the gap between screens, and
  the creator name shows for a moment when a clip starts (or when you hover). **Fill screen** covers
  each screen instead, trimming a little off the edges, but never more than a quarter of a clip.
- On phones and on short screens the options fold away behind **Settings** so the wall gets the room.
- **Rotate**: each screen swaps to a random new item every 10, 20, 30 or 60 seconds, or never. Screens
  are staggered so they don't all change at once; a thin bar on each shows its countdown.
- **Show**: clips, images (for example a creator's photo sets) or both. Images drift slowly so the
  wall never looks frozen.
- **Source**: this pull, the whole library (or the current library filter), or your faves.
- Only one screen has sound: tap a screen, or press 1 to 9, to hear it.
- **R** swaps the selected screen now (for a clip of a similar shape), **H** faves it, **M** mutes,
  **E** cycles the edge timer, **L** re-fits the wall, double-tap (or double-click) opens it full size
  in the player, **Esc** leaves.

## Edge timer

Available in the player and the cave. Pick 30 seconds on and 10 off, 60/15, 90/20, or random. When a
hold starts, everything pauses behind a full-screen **HOLD** countdown that can't be skipped by
tapping; **GO** brings it back. Rotation in the cave pauses during holds too.

## Faves

Heart a clip on its frame, in the player (H) or in the cave (H). Faves are stored on the server for
your browser, so they survive reloads and restarts. Open **Faves** to play them or run them in the cave.

## Rewards

The rank pill at the top fills up as you watch. Ranks count total time actually spent playing (holds
and paused time don't count): Lurker, Initiate (15 min), Locked In (1 h), Cave Dweller (5 h),
Edge Lord (15 h), Goon Monk (40 h), Goon God (100 h). Badges unlock for things like your first pull,
opening the cave, running 9 screens, surviving edge-timer holds and building a collection. Click the
rank pill to see your progress. Ranks never drop and there are no streaks.

Faves and rewards belong to your browser. Clearing the site's storage gives you a fresh profile.

## Where your files and data are

Everything lives in the downloads folder (`downloads/` by default, or `AIOREDGIF_DOWNLOAD_DIR`):

```
downloads/
  library/<creator>/<id>.mp4      every clip or image, stored once
  library/<creator>/<id>.json     that clip's metadata (its "sidecar")
  <pull-id>/metadata.json         every post in one pull, plus a summary
  <pull-id>/tags.json             that pull organised by tag, niche and creator
  .jobs/                          history (one file per pull)
  .faves/  .profiles/             faves and rewards, per browser
  .thumbs/                        cached poster images
```

## Getting the information you need

| You want | Look at |
|---|---|
| Everything about one clip: creator, tags, niches, duration, size, views, likes, upload date, original links | `library/<creator>/<id>.json`, or `GET /v1/library` |
| Every clip with some tags but not others | Library tag chips, or `GET /v1/library?include=a,b&exclude=c` |
| Which tags a pull contained, how often, and which files have each | `<pull-id>/tags.json`, or **Tags .json** in the results |
| A full record of a pull: what was asked, what was found, what was saved or missed | `<pull-id>/metadata.json`, or **Metadata .json** in the results |
| Tags that often appear together | `tag_pairs` in tags.json, or `GET /v1/jobs/<id>/stats` |
| Your total watch time, rank and badges | Click the rank pill, or `GET /v1/me` |
| Every pull you have made | History, or `GET /v1/history` |
| A creator's profile, top tags, posting timeline and engagement | `aioredgif info @name`, or `GET /v1/users/<name>/report` |
| Your whole library as a spreadsheet | `aioredgif export --format csv --out library.csv`, or `GET /v1/library/export?format=csv` |

The JSON files are plain text: open them in any editor, or load them in a spreadsheet or script.
Every field is explained in the [data guide](DATA.md), and the terminal commands in the
[command line guide](CLI.md).

## Bringing in files from elsewhere

Copy clips or images anywhere inside the downloads folder (for example
`downloads/library/<creator>/`) and press **Rescan folder** in the Library, or wait 30 seconds. Any
depth works, and loose files go under "unsorted". If a clip's file is named after its RedGIFs id,
aioredgif will recognise it and won't download it again.

Downloads from versions before 1.0 (kept in `downloads/<pull-id>/<creator>/`) are picked up
automatically, and their pulls appear in History.

## Troubleshooting

| Problem | What to do |
|---|---|
| Old or copied videos don't appear | Press **Rescan folder** in the Library. Check that they are inside the downloads folder the server uses (its path is logged at startup). |
| "Bad sorting order" from RedGIFs | Handled automatically: aioredgif retries with an order RedGIFs accepts. If it still fails, press **Try again**. |
| "Easy, you're going too fast" | You hit the free-tier rate limit. Wait a minute, or use an API key. |
| A pull failed half way | Press **Try again** (or Resume in History). Clips already stashed are kept. |
| No thumbnails | RedGIFs may be refusing image requests for a while; the video frame fallback still works. |
| The page looks unstyled | Make sure you open the server's own address (http://127.0.0.1:8000/), not the HTML file directly. |
