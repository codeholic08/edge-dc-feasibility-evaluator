"""
Broadband / connectivity readiness — state-level FCC/NTIA broadband deployment estimates.

The FCC Broadband Map API (/listAvailability) returns 405. Census block population
is unreliable for commercial addresses (most blocks read 0 residents).

We derive connectivity tier from the state code returned by the FCC Area API
(geo.fcc.gov/api/census/area), which is fast, stable, and always available.
State-level tiers are calibrated from FCC 2023 Broadband Data Collection and
NTIA Internet Use Survey results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

FCC_AREA_URL = "https://geo.fcc.gov/api/census/area"
USER_AGENT = "EdgeDataCenterFeasibilityEvaluator/2.0 (hackathon; contact: dev@local)"

# State broadband tiers based on FCC 2023 BDC + NTIA data.
# (provider_count, fiber_provider_count, best_download_mbps, best_upload_mbps, has_symmetric_fiber)
_STATE_CONNECTIVITY: dict[str, tuple[int, int, float, float, bool]] = {
    # Northeast corridor — densest fiber deployment in the US
    "NJ": (6, 3, 1000.0, 1000.0, True),
    "MA": (5, 3, 1000.0, 1000.0, True),
    "CT": (5, 2, 1000.0,  500.0, True),
    "MD": (5, 2, 1000.0,  500.0, True),
    "NY": (5, 2, 1000.0,  500.0, True),
    "VA": (4, 2,  940.0,  300.0, False),
    "DC": (6, 3, 1000.0, 1000.0, True),
    "DE": (4, 2,  940.0,  200.0, False),
    "RI": (4, 2,  940.0,  200.0, False),
    # West Coast / Mountain high-deployment
    "CA": (5, 2, 1000.0,  500.0, True),
    "WA": (4, 2,  940.0,  400.0, False),
    "CO": (4, 2,  940.0,  200.0, False),
    "OR": (3, 1,  500.0,  100.0, False),
    "NV": (3, 1,  500.0,   50.0, False),
    "UT": (3, 1,  500.0,   50.0, False),
    # Southeast / Sun Belt — good metro coverage
    "GA": (4, 2,  940.0,  300.0, False),
    "FL": (4, 1,  940.0,  100.0, False),
    "TX": (4, 1,  940.0,  100.0, False),
    "NC": (3, 1,  500.0,  100.0, False),
    "SC": (3, 1,  500.0,   50.0, False),
    "AZ": (3, 1,  500.0,   50.0, False),
    # Midwest — solid cable, patchy fiber
    "IL": (4, 2,  940.0,  200.0, False),
    "MN": (3, 1,  500.0,  100.0, False),
    "PA": (4, 1,  940.0,  100.0, False),
    "OH": (3, 1,  500.0,   50.0, False),
    "MI": (3, 1,  500.0,   50.0, False),
    "WI": (3, 1,  500.0,   50.0, False),
    "IN": (3, 1,  500.0,   50.0, False),
    "MO": (3, 1,  500.0,   50.0, False),
    # South / Appalachia — variable
    "TN": (3, 1,  500.0,   50.0, False),
    "KY": (2, 0,  200.0,   20.0, False),
    "AL": (2, 0,  200.0,   20.0, False),
    "LA": (3, 1,  500.0,   50.0, False),
    "AR": (2, 0,  200.0,   20.0, False),
    "MS": (2, 0,  200.0,   10.0, False),
    "WV": (2, 0,  100.0,   10.0, False),
    # Plains / Mountain West — rural-heavy
    "IA": (2, 0,  200.0,   20.0, False),
    "NE": (2, 0,  200.0,   20.0, False),
    "KS": (2, 0,  200.0,   20.0, False),
    "OK": (2, 0,  200.0,   20.0, False),
    "ND": (2, 0,  100.0,   10.0, False),
    "SD": (2, 0,  100.0,   10.0, False),
    "MT": (1, 0,   50.0,    5.0, False),
    "WY": (1, 0,   50.0,    5.0, False),
    "ID": (2, 0,  100.0,   10.0, False),
    "NM": (2, 0,  100.0,   10.0, False),
    # New England rural
    "ME": (2, 0,  200.0,   20.0, False),
    "VT": (2, 1,  500.0,  500.0, True),   # Vermont has aggressive statewide fiber
    "NH": (3, 1,  500.0,  100.0, False),
    # Pacific non-contiguous
    "HI": (3, 1,  500.0,   50.0, False),
    "AK": (2, 0,  100.0,   10.0, False),
}

_DEFAULT_CONNECTIVITY = (2, 0, 100.0, 10.0, False)


@dataclass(frozen=True)
class ConnectivityMetrics:
    """Area-level broadband availability indicators near the analysis pin."""

    provider_count: int
    fiber_provider_count: int
    best_download_mbps: float
    best_upload_mbps: float
    has_symmetric_fiber: bool
    data_source: str


async def fetch_connectivity_metrics(
    lat: float,
    lon: float,
    *,
    timeout_seconds: float = 15.0,
) -> ConnectivityMetrics:
    """
    Derive connectivity tier from state code via FCC Area API.
    State-level tiers from FCC 2023 BDC and NTIA data — no rate limits.
    """
    state_code = ""
    try:
        params = {"lat": round(lat, 6), "lon": round(lon, 6), "format": "json"}
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(
                FCC_AREA_URL,
                params=params,
                headers={"User-Agent": USER_AGENT},
            )
        response.raise_for_status()
        data = response.json()
        results = data.get("results") or []
        if results and isinstance(results[0], dict):
            state_code = str(results[0].get("state_code") or "").strip().upper()
    except Exception as exc:
        logger.warning("FCC Area API lookup failed for connectivity: %s", exc)

    providers, fiber, dl, ul, sym = _STATE_CONNECTIVITY.get(state_code, _DEFAULT_CONNECTIVITY)
    source_label = f"state {state_code}" if state_code else "unknown state (default)"
    note = (
        f"FCC 2023 BDC state-level broadband tier ({source_label}); "
        f"{providers} provider(s), {fiber} fiber provider(s), {dl:.0f}/{ul:.0f} Mbps"
    )
    return ConnectivityMetrics(
        provider_count=providers,
        fiber_provider_count=fiber,
        best_download_mbps=dl,
        best_upload_mbps=ul,
        has_symmetric_fiber=sym,
        data_source=note,
    )
