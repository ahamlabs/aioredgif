"""Brand images for the front page hero."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["Site"])

BRAND_DIR = Path(__file__).resolve().parent.parent / "static" / "brand"
BRAND_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}


@router.get("/brand")
async def brand_images() -> dict:
    """Images found in ``aioredgif/static/brand/``, in name order."""
    files = sorted(path.name for path in BRAND_DIR.glob("*") if path.suffix.lower() in BRAND_EXT)
    return {"images": [f"/brand/{name}" for name in files]}
