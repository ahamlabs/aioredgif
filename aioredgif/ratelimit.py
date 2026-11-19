"""Free-tier limits for clients of this API (per API key, else per IP)."""

from __future__ import annotations

import time

from fastapi import HTTPException, Request


class TokenBucket:
    """A token bucket per client, refilled continuously."""

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}

    def take(self, key: str, per_minute: int) -> float:
        """Spend one token for ``key``.

        Args:
            key: Who is asking (API key or IP).
            per_minute: Bucket size and refill rate.

        Returns:
            0 if the request may go ahead, else seconds until it may.
        """
        capacity = float(per_minute)
        now = time.monotonic()
        tokens, last = self._buckets.get(key, (capacity, now))
        tokens = min(capacity, tokens + (now - last) * capacity / 60.0)
        if tokens >= 1:
            self._buckets[key] = (tokens - 1, now)
            return 0.0
        self._buckets[key] = (tokens, now)
        return (1 - tokens) * 60.0 / capacity


def client_tier(request: Request) -> str:
    """Return ``"paid"`` for a known API key, else ``"free"``."""
    key = request.headers.get("X-API-Key", "")
    return "paid" if key and key in request.app.state.settings.paid_keys else "free"


async def rate_limit(request: Request) -> str:
    """FastAPI dependency: enforce the free-tier rate and return the tier.

    Raises:
        HTTPException: 429 with ``Retry-After`` when a free client is over its rate.
    """
    tier = client_tier(request)
    if tier == "paid":
        return tier
    bucket: TokenBucket = request.app.state.rate_buckets
    who = request.headers.get("X-API-Key") or (request.client.host if request.client else "anon")
    wait = bucket.take(who, request.app.state.settings.free_rpm)
    if wait:
        raise HTTPException(429, "Free tier rate limit reached", headers={"Retry-After": f"{wait:.0f}"})
    return tier
