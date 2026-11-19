"""Exports of library data as JSON, JSON Lines or CSV.

All three carry the same post records (see ``docs/DATA.md``):

* ``json``: one document ``{"schema", "generated", "posts": [...]}``;
* ``jsonl``: one post per line, easy to stream and to load in pandas or DuckDB;
* ``csv``: one post per row with lists joined by ``;`` (see :func:`creators.flatten`).
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime

from aioredgif import __version__
from aioredgif.creators import flatten, library_record
from aioredgif.library import Library
from aioredgif.tagfilter import TagFilter

FORMATS = ("json", "jsonl", "csv")
POSTS_SCHEMA = "aioredgif.posts/1"


def library_posts(
    library: Library, creator: str = "", tags: TagFilter | None = None, kind: str = "all", q: str = ""
) -> list[dict]:
    """Post records for library items matching the filters, newest upload first."""
    entries = library.search(q=q, creator=creator, kind=kind, tags=tags)
    posts = [library_record(library, entry) for entry in entries]
    posts.sort(key=lambda post: post.get("created") or "", reverse=True)
    return posts


def render(posts: Iterable[dict], fmt: str) -> Iterator[str]:
    """Yield the export text in chunks.

    Args:
        posts: Post records.
        fmt: ``"json"``, ``"jsonl"`` or ``"csv"``.

    Raises:
        ValueError: For an unknown format.
    """
    if fmt == "jsonl":
        for post in posts:
            yield json.dumps(post, ensure_ascii=False, default=str) + "\n"
    elif fmt == "json":
        document = {
            "schema": POSTS_SCHEMA,
            "generated": datetime.now(UTC).isoformat(),
            "generator": f"aioredgif {__version__}",
            "posts": list(posts),
        }
        yield json.dumps(document, ensure_ascii=False, indent=2, default=str) + "\n"
    elif fmt == "csv":
        rows = flatten(posts)
        if not rows:
            return
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            if buffer.tell() > 64_000:
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate()
        yield buffer.getvalue()
    else:
        raise ValueError(f"unknown format {fmt!r}; use one of {', '.join(FORMATS)}")


MEDIA_TYPES = {"json": "application/json", "jsonl": "application/x-ndjson", "csv": "text/csv"}
