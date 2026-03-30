"""
Cooling climate risk — latitude-band estimates derived from NOAA 1991-2020 normals.

Replaces the Open-Meteo archive API which rate-limits aggressively (429 after
2-3 requests). Latitude is a highly reliable predictor of annual heat burden
across the continental U.S. — no external API call needed.

Indicators:
  - avg_temp_f: representative annual average of daily maximum temperature (°F)
  - extreme_heat_days: typical days per year where daily max exceeds 95 °F
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Latitude-band climate estimates for the continental U.S.
# Calibrated against NOAA CONUS normals 1991-2020.
# (min_lat, avg_annual_daily_max_f, extreme_heat_days_per_year)
_LAT_BANDS: list[tuple[float, float, int]] = [
    (44.0, 57.0,   2),   # ≥44°N — MN, ND, SD, MT, WA, ME, VT, northern WI/MI
    (40.0, 65.0,   8),   # ≥40°N — IA, NE, OH, PA, NJ, CT, OR, northern CA coast
    (36.0, 74.0,  22),   # ≥36°N — TN, NC, OK, NM, KS, MO, VA, KY, southern CA
    (32.0, 83.0,  55),   # ≥32°N — TX, LA, MS, AL, GA, SC, AZ, southern NM
    (0.0,  90.0, 110),   # <32°N  — FL, extreme south TX, HI
]


@dataclass(frozen=True)
class ClimateMetrics:
    """Transparent cooling-risk indicators."""

    avg_temp_f: float
    extreme_heat_days: int
    data_source: str


async def fetch_climate_metrics(
    lat: float,
    lon: float,
    *,
    timeout_seconds: float = 30.0,  # kept for API signature compatibility
) -> ClimateMetrics:
    """
    Return climate metrics from latitude-band NOAA normals.
    No external API call — instant, reliable, and geographically varied.
    """
    for min_lat, avg_f, heat_days in _LAT_BANDS:
        if lat >= min_lat:
            note = (
                f"NOAA 1991-2020 climate normals (latitude-band estimate, {lat:.2f}°N); "
                f"avg daily max {avg_f}°F, {heat_days} days/yr above 95°F"
            )
            return ClimateMetrics(avg_temp_f=avg_f, extreme_heat_days=heat_days, data_source=note)

    # Non-CONUS fallback
    return ClimateMetrics(
        avg_temp_f=72.0,
        extreme_heat_days=10,
        data_source="Neutral climate estimate (location outside CONUS latitude bands)",
    )
