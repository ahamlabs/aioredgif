"""Response builders for media files and zip archives."""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Iterable
from pathlib import Path

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from aioredgif.archive import with_sidecars, write_zip  # noqa: F401  (re-exported for routers)

MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".m4v": "video/mp4",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def media_file(path: Path, *, inline: bool) -> FileResponse:
    """Serve a clip or image.

    Range requests are supported, so the browser player can seek.

    Args:
        path: The file.
        inline: Play in the browser (True) or download as an attachment (False).
    """
    return FileResponse(
        path,
        filename=path.name,
        media_type=MEDIA_TYPES.get(path.suffix.lower()),
        content_disposition_type="inline" if inline else "attachment",
        headers={"Cache-Control": "private, max-age=3600"},
    )


def zip_files(files: Iterable[tuple[Path, str]], filename: str) -> FileResponse:
    """Zip files into a temporary archive and send it, deleting it afterwards.

    Args:
        files: ``(path, name inside the archive)`` pairs.
        filename: Download name; unsafe characters are replaced.
    """
    handle, temp_name = tempfile.mkstemp(suffix=".zip")
    os.close(handle)
    write_zip(files, Path(temp_name))
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)[:100]
    return FileResponse(
        temp_name,
        filename=safe,
        media_type="application/zip",
        background=BackgroundTask(Path(temp_name).unlink, missing_ok=True),
    )
