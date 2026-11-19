"""Zip archives of media files and their metadata."""

from __future__ import annotations

import zipfile
from collections.abc import Iterable
from pathlib import Path


def with_sidecars(paths: Iterable[Path]) -> list[tuple[Path, str]]:
    """Archive entries for media files plus their ``.json`` sidecars, named ``creator/file``."""
    entries = []
    for path in paths:
        entries.append((path, f"{path.parent.name}/{path.name}"))
        sidecar = path.with_suffix(".json")
        if sidecar.exists():
            entries.append((sidecar, f"{path.parent.name}/{sidecar.name}"))
    return entries


def write_zip(entries: Iterable[tuple[Path, str]], target: Path) -> Path:
    """Write ``(path, name inside the archive)`` pairs to ``target``.

    Media is already compressed, so files are stored rather than deflated.

    Returns:
        ``target``.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as archive:
        for path, name in entries:
            archive.write(path, arcname=name)
    return target
