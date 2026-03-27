"""
Cooling climate risk via Open-Meteo historical weather archive.

Fetches the last full calendar year of daily maximum 2 m temperature for the pin and
derives two operational risk indicators for edge data-center cooling:
  - avg_temp_f: annual mean of daily maxima in °F
  - extreme_heat_days: days where daily max exceeded 95 °F

Higher average temperatures and more extreme heat events raise HVAC load and cooling OPEX.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def _last_full_year() -> tuple[str, str]:
    """Return (start_date, end_date) ISO strings for the last full calendar year."""
    today = datetime.date.today()
    start = datetime.date(today.year - 1, 1, 1)
    end = datetime.date(today.year - 1, 12, 31)
    return start.isoformat(), end.isoformat()


def _celsius_to_fahrenheit(c: float) -> float:
    """Convert a Celsius value to Fahrenheit."""
    return c * 9.0 / 5.0 + 32.0


@dataclass(frozen=True)
class ClimateMetrics:
    """Transparent cooling-risk indicators derived from Open-Meteo archive data."""

    avg_temp_f: float
    extreme_heat_days: int
    data_source: str


async def fetch_climate_metrics(
    lat: float,
    lon: float,
    *,
    timeout_seconds: float = 30.0,
) -> ClimateMetrics:
    """
    Query the Open-Meteo historical archive for the last full calendar year.

    Returns the annual average of daily max temperature in °F and a count of days
    where the daily max exceeded 95 °F (a standard industrial cooling stress threshold).

    Raises:
        RuntimeError: if the API returns no usable temperature observations.
    """
    start_date, end_date = _last_full_year()
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_max",
        "temperature_unit": "celsius",
        "timezone": "UTC",
    }

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.get(OPEN_METEO_ARCHIVE_URL, params=params)
    response.raise_for_status()
    data = response.json()

    daily = data.get("daily") or {}
    raw_vals = daily.get("temperature_2m_max") or []
    temps_c = [v for v in raw_vals if v is not None]

    if not temps_c:
        raise RuntimeError("Open-Meteo archive returned no temperature data for this pin")

    temps_f = [_celsius_to_fahrenheit(c) for c in temps_c]
    avg_f = round(sum(temps_f) / len(temps_f), 1)
    extreme_days = sum(1 for f in temps_f if f > 95.0)

    note = (
        f"Open-Meteo historical archive ({start_date} to {end_date}); "
        f"{len(temps_f)} daily temperature_2m_max observations"
    )
    return ClimateMetrics(avg_temp_f=avg_f, extreme_heat_days=extreme_days, data_source=note)
