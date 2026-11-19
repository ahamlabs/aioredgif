"""Rewards: ranks for total time spent watching, badges for using the features.

Profiles are kept per browser in ``<download_dir>/.profiles/<client-id>.json``.
Time is credited only while something is actually playing (the page reports
it), and each report is capped so a tab left open cannot farm ranks. Ranks go
by total time and never decay; there are no streaks to lose.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path

from aioredgif.faves import CID_RE

#: ``(seconds of total playtime, title)``, lowest first.
RANKS = [
    (0, "Lurker"),
    (15 * 60, "Initiate"),
    (60 * 60, "Locked In"),
    (5 * 3600, "Cave Dweller"),
    (15 * 3600, "Edge Lord"),
    (40 * 3600, "Goon Monk"),
    (100 * 3600, "Goon God"),
]

#: ``id: (title, how to earn it, stat it reads, threshold)``.
BADGES = {
    "first_haul": ("First haul", "Finish your first pull", "stashed", 1),
    "hoarder": ("Hoarder", "Stash 500 clips", "stashed", 500),
    "got_one": ("Got one", "Fave a clip", "faves", 1),
    "collector": ("Collector", "Keep 25 faves", "faves", 25),
    "into_cave": ("Into the cave", "Open the goon cave", "caves", 1),
    "full_wall": ("Full wall", "Run the cave on 9 screens", "max_screens", 9),
    "held_it": ("Held it", "Make it through an edge-timer hold", "edge_holds", 1),
    "iron_will": ("Iron will", "Make it through 25 holds", "edge_holds", 25),
    "connoisseur": ("Connoisseur", "Watch 100 different clips", "clips_seen", 100),
    "deep_diver": ("Deep diver", "Watch 1,000 different clips", "clips_seen", 1000),
    "tag_hunter": ("Tag hunter", "Narrow a session down by tag", "tag_filters", 1),
}

STAT_FIELDS = ("seconds", "stashed", "faves", "caves", "max_screens", "edge_holds", "tag_filters", "clips_seen")
MAX_SECONDS_PER_REPORT = 30
MAX_CLIPS_PER_REPORT = 200
MAX_HOLDS_PER_REPORT = 10


def rank_for(seconds: int) -> dict:
    """The rank for a total playtime.

    Args:
        seconds: Total seconds of playtime.

    Returns:
        ``level`` (1-based), ``title``, ``seconds``, ``next_title``, ``next_at``
        and ``progress`` (0 to 1) towards the next rank.
    """
    level = max(index for index, (need, _) in enumerate(RANKS) if seconds >= need)
    need, title = RANKS[level]
    following = RANKS[level + 1] if level + 1 < len(RANKS) else None
    return {
        "level": level + 1,
        "title": title,
        "seconds": seconds,
        "next_title": following[1] if following else None,
        "next_at": following[0] if following else None,
        "progress": round((seconds - need) / (following[0] - need), 4) if following else 1.0,
    }


def _clamp(value: object, high: int) -> int:
    return max(0, min(int(value or 0), high))


class ProfileStore:
    """Reads, updates and describes each browser's rewards profile.

    Args:
        root: The download directory.
    """

    def __init__(self, root: Path) -> None:
        self.dir = root / ".profiles"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _file(self, cid: str) -> Path:
        if not CID_RE.match(cid or ""):
            raise ValueError("bad client id")
        return self.dir / f"{cid}.json"

    def load(self, cid: str) -> dict:
        """A browser's raw profile, with defaults for anything missing."""
        profile = {
            "seconds": 0,
            "stashed": 0,
            "faves": 0,
            "caves": 0,
            "max_screens": 0,
            "edge_holds": 0,
            "tag_filters": 0,
            "seen": [],
            "badges": {},
            "since": datetime.now(UTC).isoformat(),
        }
        path = self._file(cid)
        if path.exists():
            with contextlib.suppress(json.JSONDecodeError, OSError):
                profile.update(json.loads(path.read_text(encoding="utf-8")))
        return profile

    def view(self, profile: dict) -> dict:
        """What the API shows: rank, the rank ladder, totals and every badge with progress."""
        stats = {**profile, "clips_seen": len(profile["seen"])}
        return {
            "rank": rank_for(profile["seconds"]),
            "ranks": [{"title": title, "at": seconds} for seconds, title in RANKS],
            "stats": {field: stats[field] for field in STAT_FIELDS},
            "badges": [
                {
                    "id": badge_id,
                    "title": title,
                    "how": how,
                    "earned": profile["badges"].get(badge_id),
                    "progress": min(1.0, stats[stat] / need),
                }
                for badge_id, (title, how, stat, need) in BADGES.items()
            ],
            "since": profile["since"],
        }

    async def report(self, cid: str, event: dict) -> dict:
        """Apply one batch of activity.

        Args:
            cid: The browser's client id.
            event: Activity counters; see the ``/v1/me/events`` endpoint.

        Returns:
            :meth:`view` of the updated profile, plus ``new_badges`` (list) and
            ``rank_up`` (the new rank, or None).

        Raises:
            ValueError: If a counter is not a number.
        """
        async with self._lock:
            profile = self.load(cid)
            level_before = rank_for(profile["seconds"])["level"]
            profile["seconds"] += _clamp(event.get("seconds"), MAX_SECONDS_PER_REPORT)
            seen = set(profile["seen"])
            seen.update(str(clip)[:80] for clip in (event.get("clips") or [])[:MAX_CLIPS_PER_REPORT])
            profile["seen"] = sorted(seen)
            profile["edge_holds"] += _clamp(event.get("edge_holds"), MAX_HOLDS_PER_REPORT)
            profile["stashed"] += _clamp(event.get("stashed"), 1000)
            profile["caves"] += 1 if event.get("cave_opened") else 0
            profile["max_screens"] = max(profile["max_screens"], _clamp(event.get("cave_screens"), 9))
            profile["tag_filters"] += 1 if event.get("tag_filter") else 0
            if "faves" in event:
                profile["faves"] = _clamp(event["faves"], 100_000)

            stats = {**profile, "clips_seen": len(profile["seen"])}
            now = datetime.now(UTC).isoformat()
            earned = []
            for badge_id, (title, how, stat, need) in BADGES.items():
                if badge_id not in profile["badges"] and stats[stat] >= need:
                    profile["badges"][badge_id] = now
                    earned.append({"id": badge_id, "title": title, "how": how})

            path = self._file(cid)
            temp = path.with_suffix(".part")
            temp.write_text(json.dumps(profile), encoding="utf-8")
            temp.replace(path)

            result = self.view(profile)
            result["new_badges"] = earned
            result["rank_up"] = result["rank"] if result["rank"]["level"] > level_before else None
            return result
