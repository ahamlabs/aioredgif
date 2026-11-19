"""Runtime settings, read from environment variables or a ``.env`` file.

Every field can be set with an ``AIOREDGIF_`` prefixed variable, for example
``AIOREDGIF_DOWNLOAD_DIR=/data/redgifs`` or ``AIOREDGIF_FREE_RPM=60``.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All tunable options for one aioredgif server.

    Attributes:
        api_base: Base URL of the RedGIFs API.
        site_base: Base URL of the RedGIFs website (used for Referer/Origin).
        user_agent: The User-Agent sent upstream. RedGIFs ties its temporary
            token to this value, so it is fixed for the life of the process.
        upstream_concurrency: Most upstream requests in flight at once,
            shared by every user of this server.
        upstream_min_interval: Seconds between the starts of two upstream requests.
        max_retries: Retries for one upstream API call (429/5xx/network).
        request_timeout: Timeout in seconds for one upstream request.
        download_dir: Where the library, job metadata, faves and profiles live.
        download_concurrency: Most media files downloaded at once.
        default_quality: ``"hd"`` or ``"sd"``.
        auto_resume: Continue interrupted pulls when the server starts.
        library_rescan_seconds: How often the library is re-scanned for files
            added by hand while the server runs.
        free_rpm: Requests per minute allowed per free-tier client.
        free_max_items_per_job: Most clips a free-tier client may pull per job.
        api_keys: Comma separated keys that skip the free-tier limits.
        browser_enabled: Allow the Playwright fallback.
        browser_headless: Run that browser headless.
        browser_timeout_ms: Page timeout for the browser fallback.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AIOREDGIF_", extra="ignore")

    api_base: str = "https://api.redgifs.com"
    site_base: str = "https://www.redgifs.com"
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 aioredgif/1.0"
    )

    upstream_concurrency: int = 4
    upstream_min_interval: float = 0.35
    max_retries: int = 5
    request_timeout: float = 30.0

    download_dir: Path = Path("downloads")
    download_concurrency: int = 3
    default_quality: str = "hd"
    auto_resume: bool = True
    library_rescan_seconds: float = 30.0

    free_rpm: int = 30
    free_max_items_per_job: int = 100
    api_keys: str = ""

    browser_enabled: bool = True
    browser_headless: bool = True
    browser_timeout_ms: int = 25_000

    @property
    def paid_keys(self) -> set[str]:
        """The API keys that are exempt from free-tier limits."""
        return {key.strip() for key in self.api_keys.split(",") if key.strip()}


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, read once from the environment."""
    return Settings()
