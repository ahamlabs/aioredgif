"""Include / exclude tag filtering, shared by pulls and the library.

A post passes a filter when it carries none of the excluded tags and, if any
tags are included, either one of them (``match="any"``) or all of them
(``match="all"``). Tags are compared case-insensitively, ignoring a leading
``#`` and surrounding spaces. Exclusion always wins.

Example:
    >>> TagFilter(include=["Blonde", "Solo"], exclude=["POV"]).matches(["blonde", "Teasing"])
    True
    >>> TagFilter(include=["Blonde", "Solo"], match="all").matches(["blonde", "Teasing"])
    False
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


def normalise(tag: str) -> str:
    """Canonical form of a tag for comparing: lowercase, no ``#``, trimmed."""
    return tag.strip().lstrip("#").strip().lower()


def split_tags(text: str | Iterable[str] | None) -> list[str]:
    """Turn ``"a, #b,c"`` or ``["a", "b"]`` into a de-duplicated list of tags, original case kept."""
    if not text:
        return []
    parts = text.split(",") if isinstance(text, str) else text
    seen: dict[str, str] = {}
    for part in parts:
        clean = part.strip().lstrip("#").strip()
        if clean and normalise(clean) not in seen:
            seen[normalise(clean)] = clean
    return list(seen.values())


@dataclass(frozen=True)
class TagFilter:
    """Which tags a post must have, and which it must not.

    Attributes:
        include: Tags to keep. Empty means "no requirement".
        exclude: Tags to drop. A post with any of these never passes.
        match: ``"any"`` keeps posts with at least one included tag;
            ``"all"`` keeps only posts with every included tag.
    """

    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    match: str = "any"

    def __post_init__(self) -> None:
        if self.match not in ("any", "all"):
            raise ValueError("match must be 'any' or 'all'")

    @property
    def active(self) -> bool:
        """True when the filter would remove anything."""
        return bool(self.include or self.exclude)

    def matches(self, tags: Iterable[str]) -> bool:
        """Whether a post with ``tags`` passes the filter."""
        have = {normalise(tag) for tag in tags}
        if any(normalise(tag) in have for tag in self.exclude):
            return False
        if not self.include:
            return True
        wanted = [normalise(tag) in have for tag in self.include]
        return all(wanted) if self.match == "all" else any(wanted)

    def key(self) -> str:
        """Order-independent text form, used to tell pulls with different filters apart."""
        if not self.active:
            return ""
        include = ",".join(sorted(normalise(tag) for tag in self.include))
        exclude = ",".join(sorted(normalise(tag) for tag in self.exclude))
        return f"+{include}/-{exclude}/{self.match}"

    def describe(self) -> str:
        """Short human description, e.g. ``"only blonde or solo, not pov"``."""
        parts = []
        if self.include:
            joiner = " and " if self.match == "all" else " or "
            parts.append("only " + joiner.join(self.include))
        if self.exclude:
            parts.append("not " + ", ".join(self.exclude))
        return ", ".join(parts)
