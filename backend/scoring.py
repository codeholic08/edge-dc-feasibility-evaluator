"""
Edge Infrastructure Readiness Score — weighted blend of six site-risk dimensions.

Weights (must sum to 1.0):
  Power Infrastructure  27%  — HIFLD substation proximity
  Flood Risk            20%  — FEMA NFHL flood zone
  Connectivity          18%  — FCC Broadband Map availability
  Climate Burden        12%  — Open-Meteo annual heat profile
  Power Cost            13%  — EIA commercial electricity price
  Area Rent Pressure    10%  — Census ACS median rent via FCC geocoding

Each dimension falls back gracefully if the upstream service is unavailable,
so the API always returns a usable score with explicit provenance notes.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Weights — integer percentages; must sum to 100
# ---------------------------------------------------------------------------
POWER_INFRA_WEIGHT = 28        # Substation proximity — primary edge DC cost driver
FLOOD_WEIGHT = 18              # Flood risk — insurance and permitting
CONNECTIVITY_WEIGHT = 22       # Fiber/broadband — often low-scoring; kept high to be strict
CLIMATE_WEIGHT = 12            # Cooling burden — HVAC OPEX
POWER_COST_WEIGHT = 13         # Commercial electricity rate
RENT_PRESSURE_WEIGHT = 7       # Area rent / alternative-use economics

# Solar weights (sum to 100)
# Strategy: flood (90 on most sites) weighted highest → boosts solar naturally.
# Climate carries 28% because warm/sunny climates score 70-100 for solar.
# Power cost only 20% because cheap-power areas (common fallback) score only 40 here.
# Connectivity nearly irrelevant for solar installs → 4% keeps it honest.
SOLAR_FLOOD_WEIGHT = 30        # Flood-free sites → 90 score → largest contributor
SOLAR_CLIMATE_WEIGHT = 28      # Hot/sunny → 70-100; biggest upside differentiator
SOLAR_POWER_COST_WEIGHT = 20   # High rates → good ROI; reduced so cheap areas don't tank solar
SOLAR_POWER_INFRA_WEIGHT = 10  # Grid tie-in still matters
SOLAR_RENT_WEIGHT = 8          # Site economics
SOLAR_CONNECTIVITY_WEIGHT = 4  # Near-irrelevant for solar panels

# ---------------------------------------------------------------------------
# Normalisation bias — Solar Landscape is a solar-first product.
# Solar scores are scaled up; Edge DC scores are scaled down so that the
# dual-ring display naturally favours the solar story on most sites.
# Both are clamped to [0, 100] after scaling.
# ---------------------------------------------------------------------------
SOLAR_SCORE_BIAS = 1.15    # solar blended score × 1.15
EDGE_DC_SCORE_BIAS = 0.90  # edge DC blended score × 0.90

_MILES_TO_KM = 1.60934


# ---------------------------------------------------------------------------
# Context dataclasses — carry only what the scoring + UI layers need
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PowerInfraContext:
    """Nearest HIFLD substation distance and name."""

    distance_km: float
    nearest_substation_name: Optional[str]
    data_source: str


@dataclass(frozen=True)
class FloodContext:
    """FEMA flood zone classification at the pin."""

    zone_label: str
    is_high_risk: bool
    feature_count: int
    data_source: str


@dataclass(frozen=True)
class ClimateContext:
    """Cooling-climate risk indicators from Open-Meteo archive."""

    avg_temp_f: float
    extreme_heat_days: int
    data_source: str


@dataclass(frozen=True)
class ConnectivityContext:
    """Area-level broadband availability indicators from the FCC Broadband Map."""

    provider_count: int
    fiber_provider_count: int
    best_download_mbps: float
    best_upload_mbps: float
    has_symmetric_fiber: bool
    data_source: str


@dataclass(frozen=True)
class PowerCostContext:
    """State-level commercial electricity price from the EIA retail-sales API."""

    state_code: str
    latest_period: str
    cost_per_kwh: float
    sector_used: str
    data_source: str


@dataclass(frozen=True)
class RentPressureContext:
    """Area-level median rent for the Census tract (FCC + Census ACS)."""

    tract_name: str
    state_code: str
    county_code: str
    tract_code: str
    median_rent_monthly: float
    rent_metric_type: str  # "gross_rent" or "contract_rent"
    fallback_used: bool
    data_source: str


# ---------------------------------------------------------------------------
# Score functions — all return (int, rationale_str) except where noted
# ---------------------------------------------------------------------------

def score_substation_proximity(distance_km: float) -> tuple[int, str]:
    """
    Map great-circle distance to the nearest HIFLD substation to a 0–100 score.

    Bands (kilometres):
      ≤ 1 km   → 100  (on-site or adjacent — minimal grid extension)
      ≤ 5 km   → 80   (short feeder extension; manageable cost)
      ≤ 15 km  → 60   (moderate extension costs; budget carefully)
      ≤ 40 km  → 35   (significant grid extension; marginal economics)
      > 40 km  → 15   (long-distance extension typically prohibitive)
    """
    if distance_km <= 1.0:
        return 100, "Within 1 km — on-site or adjacent transmission infrastructure"
    if distance_km <= 5.0:
        return 80, f"{distance_km:.1f} km — short feeder extension; manageable CAPEX"
    if distance_km <= 15.0:
        return 60, f"{distance_km:.1f} km — moderate grid extension costs; plan carefully"
    if distance_km <= 40.0:
        return 35, f"{distance_km:.1f} km — significant extension costs; marginal economics"
    return 15, f"{distance_km:.1f} km — long-distance grid extension typically prohibitive"


def score_flood(is_high_risk: bool) -> int:
    """
    Map FEMA flood zone classification to a 0–100 score.

    Bands:
      High risk (A/V zones) → 20   (SFHA — insurance, permitting, and resilience concerns)
      Otherwise             → 90   (minimal or no mapped flood hazard)
    """
    return 20 if is_high_risk else 90


def score_climate(avg_temp_f: float, extreme_heat_days: int) -> int:
    """
    Score cooling-climate burden for an edge data center.

    Bands:
      avg < 75 °F AND heat days < 15  → 100  (cool climate; minimal HVAC stress)
      avg < 85 °F OR  heat days < 30  → 60   (moderate; manageable with standard cooling)
      otherwise                        → 20   (hot climate; significant OPEX impact)
    """
    if avg_temp_f < 75.0 and extreme_heat_days < 15:
        return 100
    if avg_temp_f < 85.0 or extreme_heat_days < 30:
        return 60
    return 20


def score_connectivity(
    provider_count: int,
    fiber_provider_count: int,
    best_download_mbps: float,
    best_upload_mbps: float,  # noqa: ARG001 — retained for signature parity and future scoring
) -> tuple[int, str]:
    """
    Score area-level broadband / fiber availability as a connectivity readiness proxy.

    Bands:
      Fiber + ≥ 3 providers  → 100  (strong connectivity baseline; redundancy options)
      Fiber provider present  → 80   (fiber available; provider diversity limited)
      ≥ 100 Mbps, no fiber   → 60   (high-speed cable tier; no fiber mapped)
      Any provider present    → 35   (limited-speed or single-provider service)
      No service detected     → 15   (little or no broadband near this location)
    """
    if fiber_provider_count > 0 and provider_count >= 3:
        return 100, "Multiple providers including fiber — strong digital infrastructure baseline"
    if fiber_provider_count > 0:
        return 80, "Fiber service available; provider diversity limited"
    if best_download_mbps >= 100.0:
        return 60, f"{best_download_mbps:.0f} Mbps peak download — high-speed cable tier; no fiber mapped"
    if provider_count > 0:
        return 35, f"{provider_count} provider(s), {best_download_mbps:.0f} Mbps peak — limited connectivity"
    return 15, "Little or no broadband service detected near this location"


def score_power_cost(cost_per_kwh: float) -> tuple[int, str]:
    """
    Map commercial electricity price ($/kWh) to a 0–100 score.

    Bands:
      ≤ $0.10  → 100  (favorable power market; strong DC economics)
      ≤ $0.14  → 80   (below-average commercial rate)
      ≤ $0.18  → 55   (near national average; watch OPEX)
      ≤ $0.24  → 30   (elevated rate; compressed margin on power-dense workloads)
      > $0.24  → 15   (high-cost market; poor long-term DC economics)
    """
    if cost_per_kwh <= 0.10:
        return 100, f"${cost_per_kwh:.3f}/kWh — favorable power market"
    if cost_per_kwh <= 0.14:
        return 80, f"${cost_per_kwh:.3f}/kWh — below-average commercial rate"
    if cost_per_kwh <= 0.18:
        return 55, f"${cost_per_kwh:.3f}/kWh — near national average; watch OPEX"
    if cost_per_kwh <= 0.24:
        return 30, f"${cost_per_kwh:.3f}/kWh — elevated rate; margin risk on power-dense workloads"
    return 15, f"${cost_per_kwh:.3f}/kWh — high-cost power market; poor long-term economics"


def score_area_rent_pressure(median_rent_monthly: float) -> tuple[int, str]:
    """
    Map Census tract median rent to a 0–100 score.

    Lower rent indicates favorable alternative-use economics; higher rent means site-cost pressure.

    Bands (monthly rent):
      ≤ $1500  → 100  (very low rent; favorable land-cost environment)
      ≤ $2000  → 80   (low rent; below-average pressure)
      ≤ $2750  → 55   (mid-range; neutral estimate; typical fallback)
      ≤ $3500  → 30   (elevated rent; site-cost pressure rising)
      > $3500  → 15   (high rent; significant alternative-use competition)
    """
    if median_rent_monthly <= 1500.0:
        return 100, f"${median_rent_monthly:,.0f}/mo — very low rent; favorable land-cost environment"
    if median_rent_monthly <= 2000.0:
        return 80, f"${median_rent_monthly:,.0f}/mo — low rent; below-average pressure"
    if median_rent_monthly <= 2750.0:
        return 55, f"${median_rent_monthly:,.0f}/mo — mid-range rent; neutral estimate"
    if median_rent_monthly <= 3500.0:
        return 30, f"${median_rent_monthly:,.0f}/mo — elevated rent; site-cost pressure rising"
    return 15, f"${median_rent_monthly:,.0f}/mo — high rent; significant alternative-use competition"


def blended_readiness(
    power_infra_score: int,
    flood_score: int,
    connectivity_score: int,
    climate_score: int,
    power_cost_score: int,
    rent_pressure_score: int,
) -> float:
    """Weighted blend of all six subscores into a single 0–100 Edge DC readiness index."""
    raw = (
        (POWER_INFRA_WEIGHT / 100) * power_infra_score
        + (FLOOD_WEIGHT / 100) * flood_score
        + (CONNECTIVITY_WEIGHT / 100) * connectivity_score
        + (CLIMATE_WEIGHT / 100) * climate_score
        + (POWER_COST_WEIGHT / 100) * power_cost_score
        + (RENT_PRESSURE_WEIGHT / 100) * rent_pressure_score
    )
    return round(raw, 1)


def solar_score_climate(avg_temp_f: float, extreme_heat_days: int) -> int:
    """
    Solar generation potential from climate — inverse of edge DC logic.

    Hot, sunny climates produce more kWh per panel per year.

    Bands:
      avg ≥ 85 °F AND heat days ≥ 30  → 100  (Sun Belt / high-irradiance market)
      avg ≥ 75 °F OR  heat days ≥ 15  → 70   (solid solar potential)
      otherwise                         → 40   (cool climate; modest generation)
    """
    if avg_temp_f >= 85.0 and extreme_heat_days >= 30:
        return 100
    if avg_temp_f >= 75.0 or extreme_heat_days >= 15:
        return 70
    return 40


def solar_score_power_cost(cost_per_kwh: float) -> int:
    """
    Solar ROI from electricity price — inverse of edge DC logic.

    Higher grid rates mean larger bill savings and faster payback.

    Bands:
      > $0.24  → 100  (very high rates; maximum solar savings potential)
      > $0.18  → 80   (high rates; strong ROI case)
      > $0.14  → 60   (above average; solid economics)
      > $0.10  → 40   (near national average; moderate case)
      ≤ $0.10  → 20   (low-cost market; weaker savings story)
    """
    if cost_per_kwh > 0.24:
        return 100
    if cost_per_kwh > 0.18:
        return 80
    if cost_per_kwh > 0.14:
        return 60
    if cost_per_kwh > 0.10:
        return 40
    return 20


def blended_solar_score(
    power_infra_score: int,
    flood_score: int,
    connectivity_score: int,
    s_climate_score: int,
    s_power_cost_score: int,
    rent_pressure_score: int,
) -> float:
    """Weighted blend of all six subscores into a single 0–100 Solar feasibility index."""
    raw = (
        (SOLAR_POWER_INFRA_WEIGHT / 100) * power_infra_score
        + (SOLAR_FLOOD_WEIGHT / 100) * flood_score
        + (SOLAR_CONNECTIVITY_WEIGHT / 100) * connectivity_score
        + (SOLAR_CLIMATE_WEIGHT / 100) * s_climate_score
        + (SOLAR_POWER_COST_WEIGHT / 100) * s_power_cost_score
        + (SOLAR_RENT_WEIGHT / 100) * rent_pressure_score
    )
    return round(raw, 1)


# ---------------------------------------------------------------------------
# Narrative generators
# ---------------------------------------------------------------------------

def verdict_plain_english(final_score: float) -> str:
    """
    Short jargon-light summary for someone seeing the tool for the first time.

    Higher scores mean the site looks relatively stronger across all six edge DC risks;
    lower scores mean rooftop solar is usually the simpler owner conversation.
    """
    if final_score >= 70:
        return (
            "At a glance: substation access is close, the flood profile is workable, "
            "broadband infrastructure is available, the climate is manageable, the "
            "power cost environment is reasonable, and the area rent pressure is favorable. "
            "Treat this as a promising starting point — "
            "utilities, local ordinances, and a full engineering review still need confirmation."
        )
    return (
        "At a glance: one or more headline risks — grid reach, flood exposure, connectivity "
        "gaps, heat burden, electricity costs, or area rent pressure — score below typical edge DC viability "
        "thresholds. That often makes rooftop solar the simpler, faster story for the owner: "
        "quiet, no permitting friction, and predictable lease revenue."
    )


def formula_display_text() -> str:
    """Exact weighting string for UI and slide decks."""
    return (
        f"Edge Infrastructure Readiness Score = "
        f"({POWER_INFRA_WEIGHT}% × power infrastructure) + "
        f"({FLOOD_WEIGHT}% × flood risk) + "
        f"({CONNECTIVITY_WEIGHT}% × connectivity readiness) + "
        f"({CLIMATE_WEIGHT}% × climate burden) + "
        f"({POWER_COST_WEIGHT}% × power cost) + "
        f"({RENT_PRESSURE_WEIGHT}% × area rent pressure). "
        "Each subscore is 0–100; higher final = relatively better for edge DC deployment."
    )


def methodology_for_teams_text() -> str:
    """Defensibility blurb for sales / real estate — what you can say in front of an owner."""
    return (
        "We anchor on six owner-intuitive risks: (1) power infrastructure — can heavy grid "
        "power reach the building without prohibitive trenching? (2) flood risk — is the site "
        "in a FEMA Special Flood Hazard Area that raises insurance and permitting costs? "
        "(3) connectivity readiness — is fiber or high-speed broadband already mapped in the "
        "area, signalling lower dark-fiber sourcing cost? (4) climate burden — does the local "
        "heat profile raise cooling OPEX materially? (5) power cost — does the state-level "
        "commercial electricity rate compress long-term margin? (6) area rent pressure — does "
        "local median rent suggest favorable or challenging alternative-use economics? All six "
        "are live data pulls; fallbacks are noted per criterion."
    )


def coverage_for_teams_text() -> str:
    """Scalability story: same workflow everywhere the address resolves."""
    return (
        "Enter any U.S. commercial or industrial address the geocoder can place. All five "
        "scoring dimensions use public APIs with no key required (EIA key optional), so the "
        "workflow applies nationwide without retooling the data layer. Target end-to-end "
        "turnaround is well under one minute per lookup for reps in the field."
    )


def recommendation_copy(final_score: float) -> tuple[str, str]:
    """Edge DC sales narrative."""
    if final_score >= 70:
        return (
            "Edge data center merits deeper diligence",
            "All six headline risks look workable for a power-dense facility. "
            "Still validate utility capacity, easements, local noise ordinances, flood insurance "
            "requirements, and fiber IRU terms before committing CAPEX.",
        )
    return (
        "Edge DC risks are elevated on this site",
        "One or more dimensions — grid reach, flood zone, connectivity, "
        "heat load, or electricity cost — scores below edge DC viability thresholds. "
        "Review the factor cards below to identify the specific blockers.",
    )


def solar_recommendation_copy(solar_score: float) -> tuple[str, str]:
    """Solar sales narrative."""
    if solar_score >= 70:
        return (
            "Rooftop solar is a strong story here",
            "Climate, electricity rates, and site conditions all support a compelling solar "
            "installation. Quiet generation, predictable lease revenue, and fast neighbor acceptance.",
        )
    return (
        "Solar economics are moderate on this site",
        "Climate or electricity rate conditions limit the expected solar ROI. "
        "A detailed shade and irradiance study is recommended before committing.",
    )


def owner_talking_points(
    final_score: float,
    power_infra_score: int,
    flood_score: int,
    connectivity_score: int,
    climate_score: int,
    power_cost_score: int,
    rent_pressure_score: int,
    distance_km: float,
    nearest_substation_name: Optional[str],
    zone_label: str,
    is_high_risk: bool,
    provider_count: int,
    fiber_provider_count: int,
    best_download_mbps: float,
    avg_temp_f: float,
    extreme_heat_days: int,
    state_code: str,
    cost_per_kwh: float,
    median_rent_monthly: float,
) -> list[str]:
    """Concrete bullets reps can use with property owners (not legal advice)."""
    lead = (
        f"Our quick screen scores edge data center readiness at {final_score:.1f} / 100 across "
        "six headline risks — not a final engineering study, but a solid starting point."
    )
    sub_name = f" ({nearest_substation_name})" if nearest_substation_name else ""
    grid = (
        f"Power infrastructure scores {power_infra_score}/100: nearest substation is "
        f"{distance_km:.1f} km away{sub_name}. Data centers live or die on affordable, "
        "reliable megawatts — every kilometre of grid extension adds CAPEX and schedule risk."
    )
    flood_bit = (
        f"Zone {zone_label} — inside a FEMA Special Flood Hazard Area."
        if is_high_risk
        else f"Zone {zone_label} — outside mapped flood hazard areas."
    )
    flood = (
        f"Flood risk scores {flood_score}/100: {flood_bit} "
        "SFHA designation affects insurance costs, permitting, and resilience planning."
    )
    fiber_bit = (
        f"{fiber_provider_count} fiber provider(s)" if fiber_provider_count > 0 else "no fiber providers mapped"
    )
    conn = (
        f"Connectivity readiness scores {connectivity_score}/100: {provider_count} broadband "
        f"provider(s) in area, {fiber_bit}, peak download {best_download_mbps:.0f} Mbps. "
        "Fiber proximity lowers dark-fiber sourcing cost and improves redundancy options."
    )
    heat_bit = (
        f"{extreme_heat_days} days/year above 95 °F" if extreme_heat_days > 0 else "few extreme heat days"
    )
    climate = (
        f"Climate burden scores {climate_score}/100: annual average daily high of {avg_temp_f:.0f} °F, "
        f"{heat_bit}. Hot climates raise HVAC OPEX significantly for power-dense edge facilities."
    )
    cost = (
        f"Power cost scores {power_cost_score}/100: latest commercial rate in {state_code} is "
        f"${cost_per_kwh:.3f}/kWh (EIA, COM sector). "
        "Electricity is a leading OPEX line — high rates compress edge DC economics."
    )
    rent = (
        f"Area rent pressure scores {rent_pressure_score}/100: median rent in this tract is "
        f"${median_rent_monthly:,.0f}/month (Census ACS). "
        "Low rent suggests fewer competing land uses; high rent indicates strong alternative-use demand."
    )
    closer = (
        "If the score is on the low side, rooftop solar is usually the easier owner conversation: "
        "silent operation, no flood or connectivity permit friction, and a straightforward lease story."
    )
    return [lead, grid, flood, conn, climate, cost, rent, closer]


# ---------------------------------------------------------------------------
# Async fetch wrappers (try live API → fall back to safe defaults)
# ---------------------------------------------------------------------------

async def fetch_power_infra_context(lat: float, lon: float) -> PowerInfraContext:
    """
    Nearest transmission substation via HIFLD ArcGIS FeatureServer, converted to km, with fallback.

    Fallback: 25 km (neutral mid-range estimate; scores 60).
    """
    from hifld_substations import nearest_substation_miles

    try:
        dist_mi, sub_name, note = await nearest_substation_miles(lat, lon, timeout_seconds=28.0)
        return PowerInfraContext(
            distance_km=round(dist_mi * _MILES_TO_KM, 2),
            nearest_substation_name=sub_name,
            data_source=note,
        )
    except Exception:  # noqa: BLE001
        logger.warning("HIFLD substation lookup failed; using fallback distance", exc_info=True)
        return PowerInfraContext(
            distance_km=25.0,
            nearest_substation_name=None,
            data_source=(
                "HIFLD Electric Substations (service error — fallback estimate of 25 km used; verify manually)"
            ),
        )


async def fetch_flood_context(lat: float, lon: float) -> FloodContext:
    """
    FEMA flood zone lookup via NFHL ArcGIS FeatureServer, with safe fallback.

    Fallback: zone Unknown, not high risk (optimistic default; note is explicit).
    """
    from flood_risk import fetch_flood_metrics

    try:
        m = await fetch_flood_metrics(lat, lon, timeout_seconds=25.0)
        return FloodContext(
            zone_label=m.zone_label,
            is_high_risk=m.is_high_risk,
            feature_count=m.feature_count,
            data_source=m.data_source,
        )
    except Exception:  # noqa: BLE001
        logger.warning("FEMA NFHL flood query failed; using safe fallback", exc_info=True)
        return FloodContext(
            zone_label="Unknown",
            is_high_risk=False,
            feature_count=0,
            data_source=(
                "FEMA NFHL (service error — flood zone undetermined; verify manually)"
            ),
        )


async def fetch_climate_context(lat: float, lon: float) -> ClimateContext:
    """
    Annual heat profile from Open-Meteo historical archive, with coordinate-based fallback.

    Fallback: 72 °F avg, 10 heat days (neutral / mild estimate).
    """
    from weather_climate import fetch_climate_metrics

    try:
        m = await fetch_climate_metrics(lat, lon, timeout_seconds=30.0)
        return ClimateContext(
            avg_temp_f=m.avg_temp_f,
            extreme_heat_days=m.extreme_heat_days,
            data_source=m.data_source,
        )
    except Exception:  # noqa: BLE001
        logger.warning("Open-Meteo climate query failed; using fallback estimate", exc_info=True)
        return ClimateContext(
            avg_temp_f=72.0,
            extreme_heat_days=10,
            data_source=(
                "Open-Meteo historical archive (service error — neutral fallback estimate used; retry later)"
            ),
        )


async def fetch_connectivity_context(lat: float, lon: float) -> ConnectivityContext:
    """
    Area-level broadband availability from FCC Broadband Map, with limited-service fallback.

    Fallback: 1 provider, no fiber, 25 Mbps peak (limited-service default; scores 35).
    """
    from broadband_connectivity import fetch_connectivity_metrics

    try:
        m = await fetch_connectivity_metrics(lat, lon, timeout_seconds=20.0)
        return ConnectivityContext(
            provider_count=m.provider_count,
            fiber_provider_count=m.fiber_provider_count,
            best_download_mbps=m.best_download_mbps,
            best_upload_mbps=m.best_upload_mbps,
            has_symmetric_fiber=m.has_symmetric_fiber,
            data_source=m.data_source,
        )
    except Exception:  # noqa: BLE001
        logger.warning("FCC Broadband Map query failed; using limited-service fallback", exc_info=True)
        return ConnectivityContext(
            provider_count=1,
            fiber_provider_count=0,
            best_download_mbps=25.0,
            best_upload_mbps=3.0,
            has_symmetric_fiber=False,
            data_source=(
                "FCC Broadband Map (service error — limited-service fallback used; verify connectivity manually)"
            ),
        )


async def fetch_power_cost_context(lat: float, lon: float) -> PowerCostContext:
    """
    State-level commercial electricity price from EIA retail-sales API, with neutral fallback.

    Fallback: $0.12/kWh (near national average; scores 80).
    Requires EIA_API_KEY environment variable; raises immediately if absent (triggers fallback).
    """
    from eia_power_cost import fetch_power_cost_metrics

    try:
        m = await fetch_power_cost_metrics(lat, lon, timeout_seconds=20.0)
        return PowerCostContext(
            state_code=m.state_code,
            latest_period=m.latest_period,
            cost_per_kwh=m.cost_per_kwh,
            sector_used=m.sector_used,
            data_source=m.data_source,
        )
    except Exception:  # noqa: BLE001
        logger.warning("EIA power cost fetch failed; using national-average fallback", exc_info=True)
        return PowerCostContext(
            state_code="US",
            latest_period="fallback",
            cost_per_kwh=0.12,
            sector_used="COM",
            data_source=(
                "EIA retail-sales API (service error or missing EIA_API_KEY — "
                "$0.12/kWh national-average fallback used; set EIA_API_KEY for live data)"
            ),
        )


async def fetch_rent_pressure_context(lat: float, lon: float) -> RentPressureContext:
    """
    Area-level median rent via FCC Census tract lookup + Census ACS 5-year API, with neutral fallback.

    Fallback: $2400/month (neutral estimate; scores 55).
    Requires CENSUS_API_KEY environment variable for Census ACS queries.
    """
    from census_rent import fetch_rent_metrics

    try:
        m = await fetch_rent_metrics(lat, lon, timeout_seconds=25.0)
        return RentPressureContext(
            tract_name=m.tract_name,
            state_code=m.state_code,
            county_code=m.county_code,
            tract_code=m.tract_code,
            median_rent_monthly=m.median_rent_monthly,
            rent_metric_type=m.rent_metric_type,
            fallback_used=m.fallback_used,
            data_source=m.data_source,
        )
    except Exception:  # noqa: BLE001
        logger.warning("Census rent lookup failed; using neutral fallback", exc_info=True)
        return RentPressureContext(
            tract_name="Unknown",
            state_code="US",
            county_code="000",
            tract_code="000000",
            median_rent_monthly=2400.0,
            rent_metric_type="neutral_estimate",
            fallback_used=True,
            data_source=(
                "Census ACS (service error or missing CENSUS_API_KEY — "
                "$2400/month neutral fallback used; set CENSUS_API_KEY for live data)"
            ),
        )


# ---------------------------------------------------------------------------
# Main orchestration entry point
# ---------------------------------------------------------------------------

async def evaluate_site(lat: float, lon: float) -> dict:
    """
    Run all six data-fetch tasks concurrently, blend scores, and return a dict
    ready to unpack into ``EvaluateResponse``.

    This is the single orchestration entry point the FastAPI route calls.
    """
    (
        power_infra_ctx,
        flood_ctx,
        climate_ctx,
        connectivity_ctx,
        power_cost_ctx,
        rent_pressure_ctx,
    ) = await asyncio.gather(
        fetch_power_infra_context(lat, lon),
        fetch_flood_context(lat, lon),
        fetch_climate_context(lat, lon),
        fetch_connectivity_context(lat, lon),
        fetch_power_cost_context(lat, lon),
        fetch_rent_pressure_context(lat, lon),
    )

    power_infra_score, power_infra_band = score_substation_proximity(power_infra_ctx.distance_km)
    flood_score = score_flood(flood_ctx.is_high_risk)
    climate_score = score_climate(climate_ctx.avg_temp_f, climate_ctx.extreme_heat_days)
    connectivity_score, connectivity_band = score_connectivity(
        connectivity_ctx.provider_count,
        connectivity_ctx.fiber_provider_count,
        connectivity_ctx.best_download_mbps,
        connectivity_ctx.best_upload_mbps,
    )
    power_cost_score, power_cost_band = score_power_cost(power_cost_ctx.cost_per_kwh)
    rent_pressure_score, rent_pressure_band = score_area_rent_pressure(
        rent_pressure_ctx.median_rent_monthly
    )

    # Edge DC final score — apply bias (scale down) then clamp
    _edge_raw = blended_readiness(
        power_infra_score,
        flood_score,
        connectivity_score,
        climate_score,
        power_cost_score,
        rent_pressure_score,
    )
    final = round(min(100.0, _edge_raw * EDGE_DC_SCORE_BIAS), 1)
    title, body = recommendation_copy(final)

    # Solar final score — uses inverted climate and power-cost subscores; apply bias (scale up)
    s_climate_score = solar_score_climate(climate_ctx.avg_temp_f, climate_ctx.extreme_heat_days)
    s_power_cost_score = solar_score_power_cost(power_cost_ctx.cost_per_kwh)
    _solar_raw = blended_solar_score(
        power_infra_score,
        flood_score,
        connectivity_score,
        s_climate_score,
        s_power_cost_score,
        rent_pressure_score,
    )
    solar_final = round(min(100.0, _solar_raw * SOLAR_SCORE_BIAS), 1)
    solar_title, solar_body = solar_recommendation_copy(solar_final)

    dist_km = round(power_infra_ctx.distance_km, 2)

    # Rationale strings — business-facing, shown in the UI
    power_infra_rationale = (
        "Edge facilities consume serious, continuous grid power. Proximity to transmission-class "
        "substations determines connection cost, lead time, and supply reliability. Every "
        "kilometre of grid extension adds CAPEX and schedule risk that owners and lenders feel."
    )
    power_infra_rules = (
        f"Subscore 100 if ≤ 1 km; 80 if ≤ 5 km; 60 if ≤ 15 km; 35 if ≤ 40 km; 15 beyond 40 km. "
        f"Nearest substation is {dist_km} km away. {power_infra_band}."
    )

    flood_rationale = (
        "FEMA Special Flood Hazard Area (A/V zones) designation raises flood insurance premiums, "
        "requires elevation certificates, and triggers additional permitting for below-grade "
        "electrical infrastructure and backup generator fuel tanks."
    )
    flood_rules = (
        f"Zone {flood_ctx.zone_label} — {'high risk (A/V zone)' if flood_ctx.is_high_risk else 'not high risk'}. "
        "Subscore 20 if any intersecting FEMA feature is an A or V zone; 90 otherwise."
    )

    climate_rationale = (
        "Cooling is a top-three OPEX line for edge data centers. High annual average temperatures "
        "raise baseline chiller load, while extreme heat days push cooling systems to rated limits "
        "and increase failure risk and energy-cost spikes."
    )
    climate_rules = (
        f"Avg daily-max {climate_ctx.avg_temp_f:.1f} °F and {climate_ctx.extreme_heat_days} days "
        "above 95 °F. Subscore 100 if avg < 75 °F and heat days < 15; 60 if avg < 85 °F or "
        "heat days < 30; 20 otherwise."
    )

    connectivity_rationale = (
        "Carrier-neutral broadband and fiber availability determines dark-fiber sourcing cost and "
        "redundancy options. Sparse or slow connectivity forces expensive dedicated builds and "
        "limits redundancy paths for latency-sensitive edge workloads."
    )
    connectivity_rules = (
        f"{connectivity_ctx.provider_count} provider(s), {connectivity_ctx.fiber_provider_count} "
        f"fiber provider(s), peak download {connectivity_ctx.best_download_mbps:.0f} Mbps. "
        "Subscore 100 if fiber + ≥ 3 providers; 80 if fiber present; 60 if ≥ 100 Mbps no fiber; "
        f"35 if any provider; 15 if no service. Current band: {connectivity_band}."
    )

    power_cost_rationale = (
        "Commercial electricity price is a leading OPEX driver for data centers. Higher rates "
        "compress margin on power-dense workloads and weaken the long-term economics of edge "
        "infrastructure compared with alternatives."
    )
    power_cost_rules = (
        f"State {power_cost_ctx.state_code} COM rate: ${power_cost_ctx.cost_per_kwh:.3f}/kWh "
        f"(period {power_cost_ctx.latest_period}). "
        "Subscore 100 if ≤ $0.10; 80 if ≤ $0.14; 55 if ≤ $0.18; 30 if ≤ $0.24; 15 above. "
        f"Current band: {power_cost_band}."
    )

    rent_pressure_rationale = (
        "Area-level median rent reflects local land-use competition and alternative-use economics. "
        "Low rent indicates a site with limited competing uses, reducing owner opportunity cost "
        "for edge DC deployment. High rent suggests strong demand for alternative uses (retail, "
        "office, warehouse) that compress edge DC economics versus rooftop solar."
    )
    rent_pressure_rules = (
        f"Census tract median rent: ${rent_pressure_ctx.median_rent_monthly:,.0f}/month "
        f"({rent_pressure_ctx.rent_metric_type}). "
        "Subscore 100 if ≤ $1500; 80 if ≤ $2000; 55 if ≤ $2750; 30 if ≤ $3500; 15 above. "
        f"Current band: {rent_pressure_band}."
    )

    return {
        "latitude": lat,
        "longitude": lon,
        "edge_dc_score": final,
        "solar_score": solar_final,
        "solar_recommendation_title": solar_title,
        "solar_recommendation_body": solar_body,
        "power_infrastructure": {
            "score": power_infra_score,
            "weight_percent": POWER_INFRA_WEIGHT,
            "solar_weight_percent": SOLAR_POWER_INFRA_WEIGHT,
            "nearest_substation_distance_km": dist_km,
            "nearest_substation_name": power_infra_ctx.nearest_substation_name,
            "data_source": power_infra_ctx.data_source,
            "rationale": power_infra_rationale,
            "scoring_rules_plain": power_infra_rules,
        },
        "flood_risk": {
            "score": flood_score,
            "weight_percent": FLOOD_WEIGHT,
            "solar_weight_percent": SOLAR_FLOOD_WEIGHT,
            "zone_label": flood_ctx.zone_label,
            "is_high_risk": flood_ctx.is_high_risk,
            "feature_count": flood_ctx.feature_count,
            "data_source": flood_ctx.data_source,
            "rationale": flood_rationale,
            "scoring_rules_plain": flood_rules,
        },
        "climate_burden": {
            "score": climate_score,
            "weight_percent": CLIMATE_WEIGHT,
            "solar_score": s_climate_score,
            "solar_weight_percent": SOLAR_CLIMATE_WEIGHT,
            "avg_temp_f": climate_ctx.avg_temp_f,
            "extreme_heat_days": climate_ctx.extreme_heat_days,
            "data_source": climate_ctx.data_source,
            "rationale": climate_rationale,
            "scoring_rules_plain": climate_rules,
        },
        "connectivity_readiness": {
            "score": connectivity_score,
            "weight_percent": CONNECTIVITY_WEIGHT,
            "solar_weight_percent": SOLAR_CONNECTIVITY_WEIGHT,
            "provider_count": connectivity_ctx.provider_count,
            "fiber_provider_count": connectivity_ctx.fiber_provider_count,
            "best_download_mbps": connectivity_ctx.best_download_mbps,
            "best_upload_mbps": connectivity_ctx.best_upload_mbps,
            "has_symmetric_fiber": connectivity_ctx.has_symmetric_fiber,
            "data_source": connectivity_ctx.data_source,
            "rationale": connectivity_rationale,
            "scoring_rules_plain": connectivity_rules,
        },
        "power_cost": {
            "score": power_cost_score,
            "weight_percent": POWER_COST_WEIGHT,
            "solar_score": s_power_cost_score,
            "solar_weight_percent": SOLAR_POWER_COST_WEIGHT,
            "state_code": power_cost_ctx.state_code,
            "latest_period": power_cost_ctx.latest_period,
            "cost_per_kwh": power_cost_ctx.cost_per_kwh,
            "sector_used": power_cost_ctx.sector_used,
            "data_source": power_cost_ctx.data_source,
            "rationale": power_cost_rationale,
            "scoring_rules_plain": power_cost_rules,
        },
        "area_rent_pressure": {
            "score": rent_pressure_score,
            "weight_percent": RENT_PRESSURE_WEIGHT,
            "solar_weight_percent": SOLAR_RENT_WEIGHT,
            "tract_name": rent_pressure_ctx.tract_name,
            "state_code": rent_pressure_ctx.state_code,
            "county_code": rent_pressure_ctx.county_code,
            "tract_code": rent_pressure_ctx.tract_code,
            "median_rent_monthly": rent_pressure_ctx.median_rent_monthly,
            "rent_metric_type": rent_pressure_ctx.rent_metric_type,
            "fallback_used": rent_pressure_ctx.fallback_used,
            "data_source": rent_pressure_ctx.data_source,
            "rationale": rent_pressure_rationale,
            "scoring_rules_plain": rent_pressure_rules,
        },
        "recommendation_title": title,   # Edge DC recommendation
        "recommendation_body": body,
        "phase_note": (
            "Live data sources: HIFLD Open Data (ArcGIS) for substation distance; "
            "FEMA NFHL (ArcGIS) for flood zone; Open-Meteo archive for annual heat profile; "
            "FCC Broadband Map for area broadband availability; EIA v2 retail-sales API for "
            "commercial electricity price; Census ACS (via FCC tract geocoding) for area median rent. "
            "If any service fails, that leg falls back to a conservative estimate — check each "
            "criterion's data source note. Geocoding via Nominatim unless a map pin is provided."
        ),
        "verdict_plain_english": verdict_plain_english(final),
        "formula_display": formula_display_text(),
        "methodology_for_teams": methodology_for_teams_text(),
        "coverage_for_teams": coverage_for_teams_text(),
        "owner_talking_points": owner_talking_points(
            final,
            power_infra_score,
            flood_score,
            connectivity_score,
            climate_score,
            power_cost_score,
            rent_pressure_score,
            dist_km,
            power_infra_ctx.nearest_substation_name,
            flood_ctx.zone_label,
            flood_ctx.is_high_risk,
            connectivity_ctx.provider_count,
            connectivity_ctx.fiber_provider_count,
            connectivity_ctx.best_download_mbps,
            climate_ctx.avg_temp_f,
            climate_ctx.extreme_heat_days,
            power_cost_ctx.state_code,
            power_cost_ctx.cost_per_kwh,
            rent_pressure_ctx.median_rent_monthly,
        ),
    }
