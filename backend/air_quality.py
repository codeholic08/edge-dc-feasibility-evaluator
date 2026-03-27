"""
Ambient air quality via the Open-Meteo Air Quality API.

Fetches the past 7 days of hourly PM2.5 and dust concentrations (µg/m³) for the pin.
High particulate matter accelerates data-center filter replacement, degrades HVAC efficiency,
and can trigger local air-quality permit conditions for backup diesel generators.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

OPEN_METEO_AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


def _last_7_days() -> tuple[str, str]:
    """Return (start_date, end_date) ISO strings covering the 7 days ending yesterday."""
    today = datetime.date.today()
    end = today - datetime.timedelta(days=1)
    start = today - datetime.timedelta(days=7)
    return start.isoformat(), end.isoformat()


@dataclass(frozen=True)
class AirQualityMetrics:
    """7-day hourly mean PM2.5 and dust concentrations for the analysis pin."""

    avg_pm25: float
    avg_dust: float
    data_source: str


async def fetch_air_quality_metrics(
    lat: float,
    lon: float,
    *,
    timeout_seconds: float = 25.0,
) -> AirQualityMetrics:
    """
    Query Open-Meteo Air Quality API for PM2.5 and dust over the past 7 days.

    Computes simple means over all non-null hourly observations.

    Raises:
        RuntimeError: if the API returns no usable observations for either variable.
    """
    start_date, end_date = _last_7_days()
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm2_5,dust",
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "UTC",
    }

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.get(OPEN_METEO_AQ_URL, params=params)
    response.raise_for_status()
    data = response.json()

    hourly = data.get("hourly") or {}
    pm25_vals = [v for v in (hourly.get("pm2_5") or []) if v is not None]
    dust_vals = [v for v in (hourly.get("dust") or []) if v is not None]

    if not pm25_vals and not dust_vals:
        raise RuntimeError("Open-Meteo AQ returned no usable observations for this pin")

    avg_pm25 = round(sum(pm25_vals) / len(pm25_vals), 2) if pm25_vals else 10.0
    avg_dust = round(sum(dust_vals) / len(dust_vals), 2) if dust_vals else 5.0

    note = (
        f"Open-Meteo Air Quality API ({start_date} to {end_date}); "
        f"{len(pm25_vals)} PM2.5 obs, {len(dust_vals)} dust obs (hourly, µg/m³)"
    )
    return AirQualityMetrics(avg_pm25=avg_pm25, avg_dust=avg_dust, data_source=note)
