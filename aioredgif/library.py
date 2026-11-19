"""The library: every media file the server has, wherever it sits.

New downloads go to ``<download_dir>/library/<creator>/<id>.<ext>`` with a
``<id>.json`` sidecar next to them. The index also picks up:

* files you copy in by hand, at any depth, while the server runs (it re-scans
  every ``library_rescan_seconds``, or on demand);
* downloads from older versions, which kept files in ``<download_dir>/<job>/<creator>/``.

Hidden folders (``.thumbs``, ``.jobs``, ``.faves`` and so on) and ``.part``
files are ignored.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from aioredgif.models import Gif
from aioredgif.tagfilter import TagFilter

VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MEDIA_EXT = VIDEO_EXT | IMAGE_EXT
SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_name(name: str | None) -> str:
    """Make a creator handle safe to use as a folder name."""
    return SAFE_NAME.sub("_", name or "unknown")


class Library:
    """Index of media files by id, with cached metadata for browsing.

    Args:
        root: The download directory.
        rescan_seconds: Minimum seconds between automatic re-scans.
    """

    def __init__(self, root: Path, rescan_seconds: float = 30.0) -> None:
        self.root = root
        self.dir = root / "library"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.rescan_seconds = rescan_seconds
        self._index: dict[str, Path] = {}
        self._meta_cache: dict[str, tuple[float, dict]] = {}
        self._last_scan = 0.0
        self.scan()

    # --------------------------------------------------------------- index

    def scan(self) -> int:
        """Rebuild the index from disk.

        Files in ``library/`` win over copies elsewhere with the same id. When two
        different files share a name, the later one gets a short suffix so both
        stay reachable.

        Returns:
            How many media files are indexed.
        """
        index: dict[str, Path] = {}
        seen_paths: set[Path] = set()
        for top in [self.dir, *sorted(p for p in self.root.iterdir() if p.is_dir() and p != self.dir)]:
            if top.name.startswith("."):
                continue
            for folder, dirs, files in os.walk(top):
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                for name in sorted(files):
                    path = Path(folder) / name
                    if path.suffix.lower() not in MEDIA_EXT or path in seen_paths:
                        continue
                    try:
                        if path.stat().st_size == 0:
                            continue
                    except OSError:
                        continue
                    seen_paths.add(path)
                    key = path.stem.lower()
                    if key in index:
                        if top != self.dir:
                            continue  # a copy of something already in library/
                        digest = hashlib.sha1(str(path.relative_to(self.root)).encode()).hexdigest()[:6]
                        key = f"{key}-{digest}"
                    index[key] = path
        self._index = index
        self._last_scan = time.monotonic()
        return len(index)

    def refresh(self) -> None:
        """Re-scan if the last scan is older than ``rescan_seconds``."""
        if time.monotonic() - self._last_scan >= self.rescan_seconds:
            self.scan()

    def ids(self) -> list[str]:
        """All indexed ids."""
        return list(self._index)

    def get(self, gif_id: str) -> Path | None:
        """Path of a still-present, non-empty file for ``gif_id``, else None."""
        key = gif_id.lower()
        path = self._index.get(key)
        if path and path.exists() and path.stat().st_size > 0:
            return path
        self._index.pop(key, None)
        return None

    def target(self, gif: Gif, ext: str) -> Path:
        """Where a new download of ``gif`` should be written."""
        return self.dir / safe_name(gif.user_name) / f"{gif.id}.{ext}"

    def add(self, gif_id: str, path: Path) -> None:
        """Record a freshly downloaded file."""
        self._index[gif_id.lower()] = path

    def __len__(self) -> int:
        return len(self._index)

    # ------------------------------------------------------------ metadata

    def entry(self, gif_id: str) -> dict | None:
        """Browsing metadata for one file, from its sidecar when there is one.

        Files copied in without a sidecar still get an entry: the creator is the
        folder name and tags are empty.

        Returns:
            A dict with ``id, path, creator, tags, niches, duration_s, width,
            height, views, likes, created, bytes, stashed, image, thumb_src``,
            or None if the file is gone.
        """
        path = self.get(gif_id)
        if not path:
            return None
        sidecar = path.with_suffix(".json")
        stamp = sidecar.stat().st_mtime if sidecar.exists() else path.stat().st_mtime
        cached = self._meta_cache.get(gif_id.lower())
        if cached and cached[0] == stamp:
            return cached[1]
        meta: dict = {}
        if sidecar.exists():
            try:
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                meta = {}
        media = meta.get("media") or {}
        stat = path.stat()
        creator_folder = path.parent.name if path.parent != self.dir else "unsorted"
        entry = {
            "id": gif_id.lower(),
            "path": str(path),
            "creator": meta.get("creator") or creator_folder,
            "tags": meta.get("tags") or [],
            "niches": meta.get("niches") or [],
            "duration_s": meta.get("duration_s"),
            "width": meta.get("width"),
            "height": meta.get("height"),
            "views": meta.get("views"),
            "likes": meta.get("likes"),
            "created": meta.get("created"),
            "bytes": stat.st_size,
            "stashed": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "image": path.suffix.lower() in IMAGE_EXT,
            "thumb_src": media.get("thumbnail") or media.get("poster"),
        }
        self._meta_cache[gif_id.lower()] = (stamp, entry)
        return entry

    def search(
        self,
        q: str = "",
        creator: str = "",
        tag: str = "",
        kind: str = "all",
        tags: TagFilter | None = None,
    ) -> list[dict]:
        """Entries matching every given filter.

        Args:
            q: Free text matched against id, creator, tags and niches.
            creator: Exact creator handle (case-insensitive).
            tag: A single tag the entry must carry (kept for older callers;
                ``tags`` is the general form).
            kind: ``"all"``, ``"video"`` or ``"image"``.
            tags: Include / exclude tag rule.

        Returns:
            Matching entries, unsorted.
        """
        q, creator, tag = q.strip().lower(), creator.strip().lower(), tag.strip().lower()
        tags = tags or TagFilter()
        matches = []
        for gif_id in self.ids():
            entry = self.entry(gif_id)
            if not entry:
                continue
            if creator and (entry["creator"] or "").lower() != creator:
                continue
            if tag and tag not in (t.lower() for t in entry["tags"]):
                continue
            if tags.active and not tags.matches(entry["tags"]):
                continue
            if (kind == "video" and entry["image"]) or (kind == "image" and not entry["image"]):
                continue
            haystack = " ".join([entry["id"], entry["creator"] or "", *entry["tags"], *entry["niches"]]).lower()
            if q and q not in haystack:
                continue
            matches.append(entry)
        return matches
