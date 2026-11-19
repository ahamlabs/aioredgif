"""aioredgif: an async RedGIFs downloader, library and player.

The package is a FastAPI application. Run it with ``python -m aioredgif`` or
``uvicorn aioredgif.app:app``, then open http://127.0.0.1:8000/.

Typical programmatic use::

    from aioredgif.app import create_app
    from aioredgif.config import Settings

    app = create_app(Settings(download_dir="my-downloads"))
"""

__version__ = "1.0.0"
