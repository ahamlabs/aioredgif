"""Storage for faves, one JSON file per browser in ``<download_dir>/.faves``.

A browser identifies itself with a random client id (the ``X-Client-Id``
header or ``?c=``). Faves point at clips in the library; file paths never come
from the client.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path

CID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class FaveStore:
    """Reads and writes each browser's faves.

    Args:
        root: The download directory.
    """

    def __init__(self, root: Path) -> None:
        self.dir = root / ".faves"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _file(self, cid: str) -> Path:
        if not CID_RE.match(cid or ""):
            raise ValueError("bad client id")
        return self.dir / f"{cid}.json"

    def load(self, cid: str) -> dict[str, dict]:
        """All faves of one browser, keyed by clip id (empty if none or unreadable)."""
        path = self._file(cid)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    async def save(self, cid: str, data: dict[str, dict]) -> None:
        """Replace one browser's faves, atomically."""
        async with self._lock:
            path = self._file(cid)
            temp = path.with_suffix(".part")
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            temp.replace(path)

    async def add(self, cid: str, record: dict) -> dict:
        """Add or refresh a fave.

        Args:
            cid: The browser's client id.
            record: At least ``id``; usually also creator, tags and path.

        Returns:
            The stored record, with an ``added`` timestamp.
        """
        data = self.load(cid)
        record = {**record, "id": record["id"].lower(), "added": datetime.now(UTC).isoformat()}
        data[record["id"]] = record
        await self.save(cid, data)
        return record

    async def remove(self, cid: str, gif_id: str) -> bool:
        """Remove a fave. Returns False if it was not there."""
        data = self.load(cid)
        if data.pop(gif_id.lower(), None) is None:
            return False
        await self.save(cid, data)
        return True
