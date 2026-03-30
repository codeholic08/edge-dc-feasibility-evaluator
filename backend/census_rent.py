"""
Area rent pressure via FCC Census lookup + Census ACS 5-year API.

Workflow:
  1. Geocode lat/lon to Census tract via FCC Census Geography API.
  2. Query Census ACS 5-year data for median rent in that tract.
  3. Score rent pressure: lower rent = better for edge DC economics.

Rent reflects alternative-use competition and site-cost pressure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

FCC_CENSUS_URL = "https://geo.fcc.gov/api/census/area"
CENSUS_ACS_URL = "https://api.census.gov/data/2021/acs/acs5"

# FCC API does not require a key; Census ACS API requires one
# If CENSUS_API_KEY is not set, use fallback estimate


@dataclass(frozen=True)
class RentMetrics:
    """Area-level median rent for the census tract near the pin."""

    tract_name: str
    state_code: str
    county_code: str
    tract_code: str
    median_rent_monthly: float
    rent_metric_type: str  # "gross_rent" or "contract_rent"
    fallback_used: bool
    data_source: str


async def _fcc_geocode_to_tract(
    lat: float,
    lon: float,
    client: httpx.AsyncClient,
    timeout_seconds: float = 15.0,
) -> dict[str, str | int] | None:
    """
    Geocode lat/lon to Census tract via FCC Census Geography API.

    Returns dict with keys: state, county, tract, name
    Returns None if the lookup fails.
    """
    params = {"lat": lat, "lon": lon, "format": "json"}

    try:
        response = await client.get(
            FCC_CENSUS_URL,
            params=params,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.warning("FCC Census geocoding failed: %s", e)
        return None

    # FCC response structure: { "results": [ { "block_fips": "...", "state_fips": "...", ... } ] }
    results = data.get("results")
    if not results or not isinstance(results, list):
        logger.warning("FCC Census returned invalid results for (%s, %s): %s", lat, lon, type(results))
        return None

    rec = results[0] if results else {}
    if not isinstance(rec, dict):
        logger.warning("FCC Census result record is not a dict: %s", type(rec))
        return None

    # block_fips = state(2) + county(3) + tract(6) + block(4)
    block_fips = str(rec.get("block_fips") or "").strip()
    state_code = str(rec.get("state_fips") or "").strip()
    county_fips = str(rec.get("county_fips") or "").strip()

    # county_fips from FCC is the full 5-digit FIPS (state+county); extract last 3
    county_code = county_fips[-3:] if len(county_fips) >= 3 else county_fips

    # Extract tract (digits 5–10 of block_fips)
    tract_code = block_fips[5:11] if len(block_fips) >= 11 else ""

    if not state_code or not tract_code:
        logger.warning("FCC Census missing state_fips or block_fips for (%s, %s)", lat, lon)
        return None

    county_name = str(rec.get("county_name") or f"County {county_code}").strip()
    tract_name = f"Census Tract {tract_code}, {county_name}, State {state_code}"

    return {
        "state": state_code,
        "county": county_code,
        "tract": tract_code,
        "name": tract_name,
    }


async def _census_acs_query_rent(
    state: str,
    county: str,
    tract: str,
    client: httpx.AsyncClient,
    timeout_seconds: float = 15.0,
) -> tuple[float, str] | None:
    """
    Query Census ACS 5-year for median rent in the tract.

    Returns (median_rent_monthly, metric_type).
    Tries gross rent (B25064_001E) first, falls back to contract rent (B25058_001E).
    Returns None if query fails.
    """
    import os
    api_key = os.environ.get("CENSUS_API_KEY", "").strip()

    if not api_key:
        logger.warning("CENSUS_API_KEY not set; Census ACS query skipped")
        return None

    # Construct tract FIPS code: state (2) + county (3) + tract (6)
    fips_code = f"{state}{county}{tract}"

    # Try gross rent first
    for metric_code, metric_name in [("B25064_001E", "gross_rent"), ("B25058_001E", "contract_rent")]:
        params = {
            "get": f"NAME,{metric_code}",
            "for": f"tract:{tract}",
            "in": f"state:{state} county:{county}",
            "key": api_key,
        }

        try:
            response = await client.get(
                CENSUS_ACS_URL,
                params=params,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.debug("Census ACS query for %s failed: %s", metric_code, e)
            continue

        # Response structure: [["NAME", "metric"], ["tract name", "value"]]
        if not data or len(data) < 2:
            continue

        try:
            rent_value = float(data[1][1])  # Second row, second column
            if rent_value > 0:
                return rent_value, metric_name
        except (IndexError, ValueError, TypeError) as e:
            logger.debug("Failed to parse Census response: %s", e)
            continue

    logger.warning("No valid rent metric found for tract %s", fips_code)
    return None


async def fetch_rent_metrics(
    lat: float,
    lon: float,
    *,
    timeout_seconds: float = 30.0,
) -> RentMetrics:
    """
    Fetch area rent pressure from FCC + Census ACS APIs.

    Returns tract-level median rent or fallback neutral estimate.
    Never raises; always returns a RentMetrics object.
    """
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        # Step 1: geocode to tract
        tract_info = await _fcc_geocode_to_tract(lat, lon, client)

        if tract_info:
            # Step 2: query Census for rent
            rent_result = await _census_acs_query_rent(
                tract_info["state"],
                tract_info["county"],
                tract_info["tract"],
                client,
            )

            if rent_result:
                median_rent, metric_type = rent_result
                note = (
                    f"FCC Census Geography + Census ACS 5-year; tract {tract_info['tract']}; "
                    f"state {tract_info['state']}, county {tract_info['county']}; {metric_type}"
                )
                return RentMetrics(
                    tract_name=tract_info["name"],
                    state_code=tract_info["state"],
                    county_code=tract_info["county"],
                    tract_code=tract_info["tract"],
                    median_rent_monthly=median_rent,
                    rent_metric_type=metric_type,
                    fallback_used=False,
                    data_source=note,
                )

    # Fallback: neutral mid-range rent estimate ($2400/month = score 55)
    logger.warning("Rent metrics query failed; using fallback estimate")
    return RentMetrics(
        tract_name="Unknown",
        state_code="US",
        county_code="",
        tract_code="",
        median_rent_monthly=2400.0,
        rent_metric_type="fallback_neutral_estimate",
        fallback_used=True,
        data_source="Census ACS (service error or missing CENSUS_API_KEY — neutral fallback used)",
    )
