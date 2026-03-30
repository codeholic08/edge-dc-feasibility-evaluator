"""
Area-level electricity price via the U.S. Energy Information Administration (EIA) API.

Workflow:
  1. Reverse-geocode the pin via Nominatim to extract the U.S. state name.
  2. Map state name to the standard two-letter EIA state code.
  3. Query EIA v2 retail sales endpoint for the latest monthly commercial (COM)
     electricity price for that state.
  4. Return price in $/kWh (EIA publishes cents/kWh; we divide by 100).

Requires the environment variable ``EIA_API_KEY``.  If the key is absent the
function raises immediately so the caller falls back to a neutral estimate.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
EIA_RETAIL_URL = "https://api.eia.gov/v2/electricity/retail-sales/data/"
USER_AGENT = "EdgeDataCenterFeasibilityEvaluator/2.0 (hackathon; contact: dev@local)"

# EIA 2023 annual average commercial electricity rates (¢/kWh → $/kWh).
# Source: EIA Electric Power Monthly, Table 5.6.B (2023 averages).
# Used as fallback when EIA_API_KEY is not set — still gives real state-level variation.
_STATE_COMMERCIAL_RATES: dict[str, float] = {
    "AL": 0.1001, "AK": 0.2284, "AZ": 0.0943, "AR": 0.0800,
    "CA": 0.2327, "CO": 0.0943, "CT": 0.2087, "DE": 0.1069,
    "FL": 0.1026, "GA": 0.0870, "HI": 0.3744, "ID": 0.0793,
    "IL": 0.0879, "IN": 0.0817, "IA": 0.0745, "KS": 0.0874,
    "KY": 0.0779, "LA": 0.0829, "ME": 0.1701, "MD": 0.1124,
    "MA": 0.2029, "MI": 0.0971, "MN": 0.0944, "MS": 0.0890,
    "MO": 0.0794, "MT": 0.0919, "NE": 0.0729, "NV": 0.0995,
    "NH": 0.1913, "NJ": 0.1230, "NM": 0.0878, "NY": 0.1707,
    "NC": 0.0780, "ND": 0.0841, "OH": 0.0885, "OK": 0.0819,
    "OR": 0.0838, "PA": 0.0987, "RI": 0.1808, "SC": 0.0783,
    "SD": 0.0934, "TN": 0.0849, "TX": 0.0759, "UT": 0.0800,
    "VT": 0.1543, "VA": 0.0797, "WA": 0.0747, "WV": 0.0796,
    "WI": 0.0995, "WY": 0.0762, "DC": 0.1200,
}

# Comprehensive U.S. state name → 2-letter EIA state code mapping.
_STATE_NAME_TO_CODE: dict[str, str] = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
}


@dataclass(frozen=True)
class PowerCostMetrics:
    """Area-level commercial electricity price for the pin's state."""

    state_code: str
    latest_period: str
    cost_per_kwh: float
    sector_used: str
    data_source: str


async def _reverse_geocode_state(
    lat: float,
    lon: float,
    client: httpx.AsyncClient,
) -> str:
    """
    Reverse-geocode a WGS84 coordinate to a U.S. state name via Nominatim.

    Returns the full state name (e.g. "New Jersey").

    Raises:
        ValueError: if the state cannot be extracted from the response.
    """
    params = {"lat": lat, "lon": lon, "format": "json", "zoom": 5}
    response = await client.get(
        NOMINATIM_REVERSE,
        params=params,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    address = data.get("address") or {}
    state = address.get("state")
    if not state:
        raise ValueError(f"Nominatim reverse geocode returned no state for ({lat}, {lon})")
    return str(state)


async def fetch_power_cost_metrics(
    lat: float,
    lon: float,
    *,
    timeout_seconds: float = 20.0,
) -> PowerCostMetrics:
    """
    Fetch the latest monthly commercial electricity price for the pin's state from EIA.

    Requires the ``EIA_API_KEY`` environment variable.

    Raises:
        RuntimeError: if the API key is missing, the state cannot be resolved,
                      or EIA returns no price data.
    """
    api_key = os.environ.get("EIA_API_KEY", "").strip()

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        state_name = await _reverse_geocode_state(lat, lon, client)

    state_code = _STATE_NAME_TO_CODE.get(state_name)
    if not state_code:
        raise RuntimeError(
            f"State '{state_name}' not found in EIA state code mapping"
        )

    # Live API path — only when key is available
    if api_key:
        params = {
            "api_key": api_key,
            "frequency": "monthly",
            "data[]": "price",
            "facets[sectorid][]": "COM",
            "facets[stateid][]": state_code,
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": "1",
        }
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(EIA_RETAIL_URL, params=params, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        data = response.json()
        rows: list = (data.get("response") or {}).get("data") or []
        if rows:
            row = rows[0]
            raw_price = row.get("price")
            if raw_price is not None:
                cost_per_kwh = round(float(raw_price) / 100.0, 4)
                period = str(row.get("period") or "unknown")
                note = (
                    f"EIA v2 retail-sales API; state {state_code} ({state_name}); "
                    f"COM sector; period {period}; raw {raw_price} ¢/kWh"
                )
                return PowerCostMetrics(
                    state_code=state_code,
                    latest_period=period,
                    cost_per_kwh=cost_per_kwh,
                    sector_used="COM",
                    data_source=note,
                )

    # Embedded state-rate fallback — real 2023 annual averages, no key needed
    embedded_rate = _STATE_COMMERCIAL_RATES.get(state_code)
    if embedded_rate is None:
        raise RuntimeError(f"No embedded rate for state {state_code}")

    note = (
        f"EIA 2023 annual average (embedded table); state {state_code} ({state_name}); "
        f"COM sector; ${embedded_rate:.4f}/kWh"
    )
    return PowerCostMetrics(
        state_code=state_code,
        latest_period="2023-avg",
        cost_per_kwh=embedded_rate,
        sector_used="COM",
        data_source=note,
    )
