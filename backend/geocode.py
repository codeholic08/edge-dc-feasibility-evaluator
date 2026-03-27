"""
Geocode free-text addresses to WGS84 latitude/longitude.

We use OpenStreetMap Nominatim (no API key) per hackathon brief. It is polite-use only:
send a descriptive User-Agent and avoid bursty traffic in production.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
# Identifiable UA helps Nominatim operators; replace domain if you ship this.
DEFAULT_USER_AGENT = "EdgeDataCenterFeasibilityEvaluator/1.0 (hackathon; contact: dev@local)"


class GeocodeError(Exception):
    """Raised when the address cannot be resolved to coordinates."""


async def geocode_address(address: str, *, timeout_seconds: float = 25.0) -> tuple[float, float, dict[str, Any]]:
    """
    Forward-geocode ``address`` via Nominatim.

    Returns (lat, lon, raw_first_hit) where ``raw_first_hit`` is the first JSON object
    for optional debugging / display (display_name, etc.).
    """
    params = {"q": address, "format": "json", "limit": 1}
    headers = {"User-Agent": DEFAULT_USER_AGENT}

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.get(NOMINATIM_SEARCH, params=params, headers=headers)

    response.raise_for_status()
    data = response.json()
    if not data:
        raise GeocodeError(f"No results for address: {address!r}")

    hit = data[0]
    try:
        lat = float(hit["lat"])
        lon = float(hit["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        logger.exception("Unexpected Nominatim payload: %s", hit)
        raise GeocodeError("Malformed geocoder response") from exc

    return lat, lon, hit
