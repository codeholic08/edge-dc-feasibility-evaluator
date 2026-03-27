"""
Resilient Overpass API client with endpoint rotation and per-mirror timeout.

The public overpass-api.de instance is frequently overloaded (504) or rate-limits
aggressive clients (429). This module tries a ranked list of public mirrors in
sequence with a short per-mirror timeout so a hanging mirror never blocks the
whole request for the full query timeout.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

# Ranked list of public Overpass mirrors — primary first, then fallbacks.
OVERPASS_ENDPOINTS: list[str] = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

USER_AGENT = "EdgeDataCenterFeasibilityEvaluator/2.0 (hackathon; +https://openstreetmap.org/copyright)"

# Max seconds to wait for any single mirror before moving to the next.
_PER_MIRROR_TIMEOUT = 15.0

# Seconds to wait after a 429 before trying the next endpoint.
_RATE_LIMIT_BACKOFF = 1.5

# 4xx codes that indicate the mirror itself is blocking us (not a bad query).
_MIRROR_BLOCK_CODES = {401, 403, 407}


async def overpass_post(
    query: str,
    *,
    client: httpx.AsyncClient,
    label: str = "query",
) -> dict:
    """
    POST an Overpass QL query, rotating through all known mirrors on errors.

    Each mirror is given at most ``_PER_MIRROR_TIMEOUT`` seconds. 5xx and
    mirror-block 4xx codes (401, 403, 407) are skipped silently; 429 gets a
    short back-off before moving on. Only a genuine 400 (malformed query) is
    re-raised immediately. Raises ``RuntimeError`` if every mirror fails.

    Args:
        query: Full Overpass QL string (including ``[out:json][timeout:...]``).
        client: Caller-owned AsyncClient reused across queries in one cycle.
        label: Short description used in log messages.

    Returns:
        Parsed JSON response dict.
    """
    last_exc: Exception | None = None

    for url in OVERPASS_ENDPOINTS:
        try:
            response = await asyncio.wait_for(
                client.post(url, data={"data": query}, headers={"User-Agent": USER_AGENT}),
                timeout=_PER_MIRROR_TIMEOUT,
            )

            if response.status_code == 429:
                logger.warning(
                    "Overpass %s: 429 from %s — backing off %.1fs then trying next mirror",
                    label, url, _RATE_LIMIT_BACKOFF,
                )
                await asyncio.sleep(_RATE_LIMIT_BACKOFF)
                last_exc = httpx.HTTPStatusError(
                    f"429 from {url}", request=response.request, response=response
                )
                continue

            if response.status_code in _MIRROR_BLOCK_CODES:
                logger.warning(
                    "Overpass %s: %s from %s — mirror blocked, trying next",
                    label, response.status_code, url,
                )
                last_exc = httpx.HTTPStatusError(
                    f"{response.status_code} from {url}", request=response.request, response=response
                )
                continue

            if response.status_code >= 500:
                logger.warning(
                    "Overpass %s: %s from %s — trying next mirror",
                    label, response.status_code, url,
                )
                last_exc = httpx.HTTPStatusError(
                    f"{response.status_code} from {url}", request=response.request, response=response
                )
                continue

            # 400 = bad query, not a mirror issue — raise immediately
            response.raise_for_status()
            return response.json()

        except (asyncio.TimeoutError, httpx.TimeoutException) as exc:  # noqa: BLE001
            logger.warning("Overpass %s: timeout on %s — trying next mirror", label, url)
            last_exc = exc
            continue
        except httpx.HTTPStatusError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Overpass %s: error on %s: %s — trying next mirror", label, url, exc)
            last_exc = exc
            continue

    raise RuntimeError(f"All Overpass mirrors failed for {label}") from last_exc
