"""JSON metadata written next to downloads.

Layout under the download directory::

    library/<creator>/<id>.mp4    every clip, stored once and shared by all pulls
    library/<creator>/<id>.json   sidecar: that clip's record (see gif_record)
    <job>/metadata.json           every post in a pull, plus a summary
    <job>/tags.json               tag -> count, share and files; niche and creator breakdowns

File paths inside the JSON are relative to the download directory.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from aioredgif.library import safe_name
from aioredgif.models import FileResult, Gif, JobStatus

SITE = "https://www.redgifs.com"


def gif_record(gif: Gif, result: FileResult | None, root: Path) -> dict:
    """Everything known about one post, as stored in sidecars and metadata.json.

    Args:
        gif: The post.
        result: Its download result, if any.
        root: The download directory (file paths are made relative to it).

    Returns:
        A JSON-ready dict: links, creator, tags, niches, how it was found,
        size and stats, media URLs, the saved file, its status, and the full
        upstream object under ``raw``.
    """
    file_rel = None
    if result and result.path:
        try:
            file_rel = Path(result.path).relative_to(root).as_posix()
        except ValueError:
            file_rel = result.path
    if result is None:
        status = None
    elif result.error:
        status = "failed"
    else:
        status = "skipped" if result.skipped else "saved"
    return {
        "id": gif.id,
        "page_url": f"{SITE}/watch/{gif.id}",
        "creator": gif.user_name,
        "creator_url": f"{SITE}/users/{gif.user_name}" if gif.user_name else None,
        "tags": gif.tags,
        "niches": gif.niches,
        "description": gif.description,
        "found_via": gif.sources,
        "type": "image" if gif.is_image else "video",
        "duration_s": gif.duration,
        "width": gif.width,
        "height": gif.height,
        "has_audio": gif.has_audio,
        "views": gif.views,
        "likes": gif.likes,
        "verified": gif.verified,
        "created": gif.created.isoformat() if gif.created else None,
        "media": gif.urls.model_dump(exclude_none=True),
        "file": file_rel,
        "bytes": result.bytes if result else None,
        "status": status,
        "error": result.error if result else None,
        "raw": gif.raw,
    }


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temp.replace(path)


def write_sidecar(gif: Gif, result: FileResult, root: Path) -> None:
    """Write ``<id>.json`` next to the post's file (or where it would have gone)."""
    if result.path:
        target = Path(result.path).with_suffix(".json")
    else:
        target = root / "library" / safe_name(gif.user_name) / f"{gif.id}.json"
    _write_json(target, gif_record(gif, result, root))


def compute_stats(records: list[dict]) -> dict:
    """Tag, niche and creator breakdowns.

    Args:
        records: :func:`gif_record` dicts, or job items (which use ``user_name``).

    Returns:
        Counts, shares, the 25 most common tag pairs, plus private ``_by_tag``
        and ``_by_niche`` id lists used to build tags.json.
    """
    tags: Counter[str] = Counter()
    niches: Counter[str] = Counter()
    creators: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    by_tag: dict[str, list[str]] = defaultdict(list)
    by_niche: dict[str, list[str]] = defaultdict(list)
    duration = 0.0
    total_bytes = 0
    for record in records:
        record_tags = sorted(dict.fromkeys(record.get("tags") or []))
        for tag in record_tags:
            tags[tag] += 1
            by_tag[tag].append(record["id"])
        for index, first in enumerate(record_tags):
            for second in record_tags[index + 1 :]:
                pairs[(first, second)] += 1
        for niche in record.get("niches") or []:
            niches[niche] += 1
            by_niche[niche].append(record["id"])
        creator = record.get("creator") or record.get("user_name")
        if creator:
            creators[creator] += 1
        duration += record.get("duration_s") or 0
        total_bytes += record.get("bytes") or 0

    count = len(records)
    return {
        "posts": count,
        "unique_tags": len(tags),
        "total_duration_s": round(duration, 1),
        "total_bytes": total_bytes,
        "tags": [
            {"tag": tag, "count": hits, "share": round(hits / count, 3) if count else 0}
            for tag, hits in tags.most_common()
        ],
        "niches": [{"niche": niche, "count": hits} for niche, hits in niches.most_common()],
        "creators": [{"creator": creator, "count": hits} for creator, hits in creators.most_common()],
        "tag_pairs": [{"tags": list(pair), "count": hits} for pair, hits in pairs.most_common(25)],
        "_by_tag": by_tag,
        "_by_niche": by_niche,
    }


def write_job_metadata(job: JobStatus, gifs: list[Gif], job_dir: Path, root: Path) -> None:
    """Write a finished pull's metadata.json and tags.json into ``job_dir``."""
    results = {result.id: result for result in job.files}
    records = [gif_record(gif, results.get(gif.id), root) for gif in gifs]
    stats = compute_stats(records)
    by_tag, by_niche = stats.pop("_by_tag"), stats.pop("_by_niche")
    files = {record["id"]: record["file"] for record in records}
    now = datetime.now(UTC).isoformat()

    def listing(ids: list[str]) -> list[dict]:
        return [{"id": gif_id, "file": files.get(gif_id)} for gif_id in ids]

    _write_json(
        job_dir / "metadata.json",
        {
            "generated": now,
            "job": {"id": job.id, "created": job.created.isoformat(), "request": job.request.model_dump()},
            "summary": stats,
            "items": records,
        },
    )
    _write_json(
        job_dir / "tags.json",
        {
            "generated": now,
            "job": job.id,
            "tags": {
                entry["tag"]: {"count": entry["count"], "share": entry["share"], "items": listing(by_tag[entry["tag"]])}
                for entry in stats["tags"]
            },
            "niches": {
                entry["niche"]: {"count": entry["count"], "items": listing(by_niche[entry["niche"]])}
                for entry in stats["niches"]
            },
            "creators": {entry["creator"]: entry["count"] for entry in stats["creators"]},
            "tag_pairs": stats["tag_pairs"],
        },
    )


def live_stats(job: JobStatus) -> dict:
    """Stats for a pull that may still be running, from its list of found posts."""
    stats = compute_stats([item.model_dump() for item in job.items])
    stats.pop("_by_tag")
    stats.pop("_by_niche")
    return stats
