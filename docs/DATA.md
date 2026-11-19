# Data guide

This page covers what aioredgif knows about creators and posts, how it is packaged, and how to get it
from the web app, the HTTP API or the command line. Field names stay stable within a schema version,
so you can build on them.

## What developers usually want

| Need | Where it comes from |
|---|---|
| A creator's profile: handle, display name, profile image, bio, followers, views, join date | `creator` block of a creator report |
| How much they post: total posts, clips, images, footage length | `summary.posts`, `videos`, `images`, `duration_s` |
| What they post about: most used tags, tag pairs, niches, when each tag was first and last used | `summary.tags`, `tag_pairs`, `niches` |
| When they post: first and last upload, uploads per month, weekday and hour, average gap | `summary.timeline` |
| What does well: views, likes, like rate, most viewed and most liked posts | `summary.views`, `likes`, `like_rate`, `most_viewed`, `most_liked` |
| How to get each file: HD and SD links, the API call and the CLI command | `posts[].download` |
| What is already on disk, and where | `posts[].file`, `bytes`; `summary.in_library` |
| A flat table for pandas, a spreadsheet or a database | `export --format csv` or `jsonl` |
| Everything RedGIFs returned, for fields aioredgif does not name yet | `raw` on every profile and post |

Typical uses are creator analytics dashboards, archiving with a searchable index, tag and trend
research, and deduplicating or organising a collection.

## Getting the data

| | Web app | HTTP API | Command line |
|---|---|---|---|
| Live creator report | | `GET /v1/users/{name}/report?limit=200&posts=true` | `aioredgif info @name --json` |
| Reports for every creator in your library | | `GET /v1/library/creators?posts=false` | `aioredgif export --creators` |
| Library posts as JSON / JSONL / CSV | | `GET /v1/library/export?format=csv&include=&exclude=&creator=&kind=` | `aioredgif export --format csv` |
| One pull's metadata and tag stats | Results → metadata buttons | `GET /v1/jobs/{id}/metadata?kind=all\|tags` | the `.zip` from `pull --zip` |
| A sidecar for one file | | | `library/<creator>/<id>.json` on disk |

Live reports read RedGIFs at the polite pace described in the [user guide](USER_GUIDE.md); library
reports and exports only read your disk and cost nothing upstream.

```bash
aioredgif info @someone --json > someone.json          # full report on stdout
aioredgif info @someone --out someone.json             # write the file, show the summary
aioredgif export --format csv --out library.csv        # one row per post
aioredgif export --format jsonl --include blonde --exclude pov | jq .id
```

## Creator report (`aioredgif.creator/1`)

```jsonc
{
  "schema": "aioredgif.creator/1",
  "generated": "2026-11-20T10:00:00+00:00",   // UTC, ISO 8601
  "generator": "aioredgif 1.0.0",
  "source": "redgifs",                         // or "library" for reports built from local files
  "complete": true,                            // false when --limit cut the post list short
  "creator": { ... },
  "summary": { ... },
  "posts": [ ... ]                             // left out with --no-posts / posts=false
}
```

### `creator`

| Field | Type | Meaning |
|---|---|---|
| `username` | string | The handle used in profile links |
| `display_name` | string or null | The name shown on the profile |
| `profile_url` | string | `https://www.redgifs.com/users/<username>` |
| `profile_image` | string or null | URL of the profile picture |
| `description` | string or null | Profile bio |
| `verified` | bool or null | RedGIFs verified badge |
| `followers`, `following` | int or null | Follower counts |
| `views`, `likes` | int or null | Profile-wide totals as RedGIFs reports them |
| `total_posts` | int or null | Published posts according to the profile |
| `published_collections` | int or null | Collections on the profile |
| `joined` | ISO date or null | When the account was created |
| `links` | any or null | Social links, if the profile lists any |
| `raw` | object | The profile exactly as RedGIFs returned it |

RedGIFs does not document its API, so profile names are read from several known spellings. Anything
missing is `null`; `raw` always has the original.

### `summary`

| Field | Meaning |
|---|---|
| `posts`, `videos`, `images`, `with_audio` | Counts over the posts read |
| `orientation` | `{"portrait": n, "landscape": n, "square": n}` |
| `resolutions` | Ten most common `WIDTHxHEIGHT`, with counts |
| `duration_s`, `views`, `likes` | Each `{total, mean, median, min, max}`, or null when unknown |
| `like_rate` | Total likes divided by total views |
| `unique_tags`, `tags_per_post` | How varied the tagging is |
| `tags` | Every tag, most used first: `tag`, `count`, `share` (of posts), `first_used`, `last_used` |
| `tag_pairs` | The 25 tag pairs that appear together most often: `tags`, `count` |
| `niches` | Niches the posts belong to, with counts |
| `timeline.first_upload`, `last_upload` | ISO timestamps |
| `timeline.active_days` | Days between first and last upload |
| `timeline.mean_days_between_uploads` | Average posting gap |
| `timeline.by_month` | `{"2026-06": 14, ...}` |
| `timeline.by_weekday`, `by_hour_utc` | Posting rhythm |
| `most_viewed`, `most_liked` | Top ten: `id`, the number, `page_url` |
| `in_library`, `total_bytes_in_library` | How much of this is already downloaded |

### `posts[]`

Each post is the sidecar record (below) plus:

| Field | Meaning |
|---|---|
| `orientation` | `portrait`, `landscape` or `square` |
| `download.hd`, `download.sd` | Direct media URLs. They are signed and expire, so fetch soon or re-read |
| `download.api` | The aioredgif endpoint that streams it |
| `download.cli` | The command that downloads it into the library |

## Post record and sidecars

Every downloaded file has a sidecar next to it: `library/<creator>/<id>.json`. Exports and reports use
the same fields.

| Field | Meaning |
|---|---|
| `id` | RedGIFs id (also the file name) |
| `page_url`, `creator`, `creator_url` | Where it lives and who posted it |
| `tags`, `niches`, `description` | As tagged on RedGIFs |
| `found_via` | The pull sources that found it (`user:x`, `niche:y`, `tag:z`) |
| `type` | `video` or `image` |
| `duration_s`, `width`, `height`, `has_audio` | Media facts |
| `views`, `likes`, `verified` | Engagement at the time it was read |
| `created` | Upload time, ISO 8601 |
| `media` | `hd`, `sd`, `thumbnail`, `poster`... as RedGIFs listed them |
| `file`, `bytes` | Path relative to the download folder, and size |
| `status`, `error` | `saved`, `skipped` or `failed` (sidecars and pull metadata only) |
| `raw` | The full upstream object |

### Library exports (`aioredgif.posts/1`)

- `json`: `{"schema": "aioredgif.posts/1", "generated": ..., "generator": ..., "posts": [...]}`
- `jsonl`: one post record per line, nothing else; easy to stream
- `csv`: one row per post with the columns `id, creator, type, created, duration_s, width, height,
  orientation, has_audio, views, likes, tags, niches, description, page_url, file, bytes, hd_url,
  sd_url, thumbnail_url`. `tags` and `niches` are joined with `;`.

### Per pull

Each pull's folder (`downloads/<pull-id>/`) has `metadata.json` (the request, the totals and every post
record) and `tags.json` (tag, pair, niche and creator counts with the ids under each tag). Both go
into the pull's `.zip`.

## Versioning

The schema name changes (`/2`) only when a field is removed or changes meaning. New fields can appear
within a version, so ignore keys you do not know. `raw` follows RedGIFs and can change at any time.

## Rate limits and being polite

Live reports cost one request per 80 posts plus one for the profile. The server's free tier allows
`AIOREDGIF_FREE_RPM` requests a minute per client, and everything upstream goes through the same
throttle as downloads. For big studies, pull once and analyse the library, which costs nothing.

## What this data is not for

The reports describe public posting activity, which suits analytics, archiving and research. Two uses
need more than this tool can give you:

- **Training AI models on the media.** The clips show real, identifiable people. Training generative
  or recognition models on them needs those people's consent and a licence for the content, and
  RedGIFs' terms forbid scraping for that. aioredgif does not package media as a training set, and
  this guide does not describe one. Tag statistics and aggregate numbers, with no media, are a
  different matter, but check the terms before you publish anything.
- **Identifying or tracking people.** Do not link creators' accounts to other identities or follow
  them across sites.

Respect takedown requests: if a creator asks for content to be removed, delete it from your library
and any exports.
