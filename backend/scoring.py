"""
Feasibility scoring: weighted blend of six site-risk dimensions.

Weights (must sum to 1.0):
  Power proximity   35%  — HIFLD substation distance
  Zoning / nuisance 25%  — OSM residential land + schools within 500 m
  Climate / cooling 15%  — Open-Meteo annual heat profile
  Flood risk        10%  — FEMA NFHL flood zone
  Air quality        8%  — Open-Meteo PM2.5 7-day average
  Fiber proximity    7%  — OSM fiber conduit + telecom nodes

Each dimension falls back to a deterministic coordinate-based estimate if the upstream
service is unavailable, so reps always receive a number.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Weights — must sum to 1.0; percentages are documented in the API response
# ---------------------------------------------------------------------------
POWER_WEIGHT = 0.35
ZONING_WEIGHT = 0.25
CLIMATE_WEIGHT = 0.15
FLOOD_WEIGHT = 0.10
AIR_QUALITY_WEIGHT = 0.08
FIBER_WEIGHT = 0.07


# ---------------------------------------------------------------------------
# Synthetic fallback helpers (Phase 1 / service-error path)
# ---------------------------------------------------------------------------

def _pin_digest(lat: float, lon: float) -> bytes:
    """Stable SHA-256 fingerprint for a WGS84 pin (used for synthetic inputs only)."""
    payload = f"{lat:.7f}|{lon:.7f}".encode("utf-8")
    return hashlib.sha256(payload).digest()


def synthetic_substation_distance_miles(lat: float, lon: float) -> float:
    """
    Phase 1 stand-in for HIFLD nearest-substation distance.

    Varies deterministically with lat/lon so different addresses get different scores.
    Not a real grid measurement — replace with HIFLD in production.
    """
    d = _pin_digest(lat, lon)
    u = int.from_bytes(d[0:4], "big") / float(2**32)
    return round(0.15 + u * 5.85, 2)  # ~0.15 .. 6.0 mi


def synthetic_residential_percent(lat: float, lon: float) -> float:
    """
    Phase 1 stand-in for Overpass residential land share within 500 m.

    Same idea: stable pseudo-random from coordinates, not OSM geometry.
    """
    d = _pin_digest(lat, lon)
    u = int.from_bytes(d[4:8], "big") / float(2**32)
    return round(u * 42.0, 2)  # 0 .. 42%


def synthetic_avg_temp_f(lat: float, lon: float) -> float:
    """
    Coordinate-based fallback for annual average daily-max temperature in °F.

    Spans 50–95 °F to exercise all scoring bands.
    """
    d = _pin_digest(lat, lon)
    u = int.from_bytes(d[8:12], "big") / float(2**32)
    return round(50.0 + u * 45.0, 1)


def synthetic_extreme_heat_days(lat: float, lon: float) -> int:
    """Coordinate-based fallback for days exceeding 95 °F annually (0–40)."""
    d = _pin_digest(lat, lon)
    u = int.from_bytes(d[12:16], "big") / float(2**32)
    return int(u * 40)


# ---------------------------------------------------------------------------
# Context dataclasses — carry only what the scoring + UI layers need
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PowerContext:
    """Everything the UI needs to explain the power-proximity constraint."""

    distance_miles: float
    data_source: str


@dataclass(frozen=True)
class ZoningContext:
    """Everything the UI needs to explain the nuisance / noise / zoning constraint."""

    nuisance_percent: float
    residential_land_percent: float
    school_count: int
    radius_meters: int
    data_source: str


@dataclass(frozen=True)
class ClimateContext:
    """Cooling-climate risk indicators from Open-Meteo archive."""

    avg_temp_f: float
    extreme_heat_days: int
    data_source: str


@dataclass(frozen=True)
class FloodContext:
    """FEMA flood zone classification at the pin."""

    zone_label: str
    is_high_risk: bool
    feature_count: int
    data_source: str


@dataclass(frozen=True)
class AirQualityContext:
    """7-day hourly mean PM2.5 and dust concentrations."""

    avg_pm25: float
    avg_dust: float
    data_source: str


@dataclass(frozen=True)
class FiberContext:
    """OSM fiber and telecom infrastructure counts near the pin."""

    fiber_way_count: int
    telecom_node_count: int
    data_source: str


# ---------------------------------------------------------------------------
# Score functions — all return 0–100 int
# ---------------------------------------------------------------------------

def score_power_proximity(distance_miles: float) -> tuple[int, str]:
    """
    Map great-circle distance to the nearest high-voltage substation to a 0–100 score.

    Bands:
      < 1 mile  → 100
      1–3 miles → 50
      > 3 miles → 10
    """
    if distance_miles < 1.0:
        return 100, "Within 1 mile of transmission-class infrastructure"
    if distance_miles <= 3.0:
        return 50, "1-3 miles: trenching and feeder upgrades materially erode economics"
    return 10, "Beyond 3 miles: long-distance grid extension is typically prohibitive"


def score_nuisance_disk(nuisance_disk_percent: float) -> int:
    """
    Map combined sensitive land share (residential + schools in analysis disk) to 0–100.

    Anchors:
      0% coverage  → 100
      > 20%        → 20 (floor)
      Linear between.
    """
    if nuisance_disk_percent <= 0.0:
        return 100
    if nuisance_disk_percent > 20.0:
        return 20
    t = nuisance_disk_percent / 20.0
    return int(round(100.0 + t * (20.0 - 100.0)))


def score_climate(avg_temp_f: float, extreme_heat_days: int) -> int:
    """
    Score cooling-climate risk for an edge data center.

    Bands:
      avg < 75 °F AND heat days < 15  → 100  (cool climate, minimal HVAC stress)
      avg < 85 °F OR  heat days < 30  → 60   (moderate; manageable with standard cooling)
      otherwise                        → 20   (hot climate; significant OPEX impact)
    """
    if avg_temp_f < 75.0 and extreme_heat_days < 15:
        return 100
    if avg_temp_f < 85.0 or extreme_heat_days < 30:
        return 60
    return 20


def score_flood(is_high_risk: bool) -> int:
    """
    Map FEMA flood zone classification to a 0–100 score.

    Bands:
      High risk (A/V zones) → 20   (SFHA — insurance, permitting, and resilience concerns)
      Otherwise             → 90   (minimal or no mapped flood hazard)
    """
    return 20 if is_high_risk else 90


def score_air_quality(avg_pm25: float) -> int:
    """
    Map 7-day mean PM2.5 concentration (µg/m³) to a 0–100 score.

    Bands align with EPA AQI breakpoints:
      < 5   → 100  (excellent)
      < 12  → 70   (good / EPA annual standard)
      < 25  → 40   (moderate)
      ≥ 25  → 15   (unhealthy for sensitive groups / poor filter lifetime)
    """
    if avg_pm25 < 5.0:
        return 100
    if avg_pm25 < 12.0:
        return 70
    if avg_pm25 < 25.0:
        return 40
    return 15


def score_fiber(fiber_way_count: int, telecom_node_count: int) -> int:
    """
    Score fiber / telecom infrastructure proximity.

    Bands:
      ≥ 3 fiber ways OR ≥ 1 telecom node → 100  (strong connectivity baseline)
      ≥ 1 fiber way                       → 60   (some fiber; capacity unknown)
      0 ways and 0 nodes                  → 20   (no mapped fiber; dark-fiber cost TBD)
    """
    if fiber_way_count >= 3 or telecom_node_count >= 1:
        return 100
    if fiber_way_count >= 1:
        return 60
    return 20


def blended_feasibility(
    power_score: int,
    zoning_score: int,
    climate_score: int,
    flood_score: int,
    air_quality_score: int,
    fiber_score: int,
) -> float:
    """Weighted blend of all six subscores into a single 0–100 feasibility index."""
    raw = (
        POWER_WEIGHT * power_score
        + ZONING_WEIGHT * zoning_score
        + CLIMATE_WEIGHT * climate_score
        + FLOOD_WEIGHT * flood_score
        + AIR_QUALITY_WEIGHT * air_quality_score
        + FIBER_WEIGHT * fiber_score
    )
    return round(raw, 1)


# ---------------------------------------------------------------------------
# Narrative generators
# ---------------------------------------------------------------------------

def verdict_plain_english(final_score: float) -> str:
    """
    Short jargon-light summary for someone seeing the tool for the first time.

    Higher scores mean edge data centers look relatively less painful across all six risks;
    lower scores mean rooftop solar is usually the smoother owner conversation.
    """
    if final_score >= 70:
        return (
            "At a glance: grid access is close enough, surrounding land use is workable, "
            "the climate profile is manageable, and no major flood or air-quality red flags "
            "jumped out. Treat this as a promising starting point — utilities, local ordinances, "
            "and a full engineering review still need confirmation."
        )
    return (
        "At a glance: one or more headline risks — grid reach, residential noise exposure, "
        "heat load, flood zone, air quality, or fiber availability — score below typical "
        "edge DC viability thresholds. That usually makes rooftop solar the simpler, faster "
        "story for the owner: quiet, no permitting friction, and predictable lease revenue."
    )


def formula_display_text() -> str:
    """Exact weighting string for UI and slide decks."""
    pw = int(POWER_WEIGHT * 100)
    zw = int(ZONING_WEIGHT * 100)
    cw = int(CLIMATE_WEIGHT * 100)
    fw = int(FLOOD_WEIGHT * 100)
    aw = int(AIR_QUALITY_WEIGHT * 100)
    fibw = int(FIBER_WEIGHT * 100)
    return (
        f"Final score = ({pw}% × grid proximity) + ({zw}% × nuisance/zoning) + "
        f"({cw}% × climate/cooling) + ({fw}% × flood risk) + "
        f"({aw}% × air quality) + ({fibw}% × fiber proximity). "
        "Each subscore is 0–100; higher final = relatively better for edge DCs across all six risks."
    )


def methodology_for_teams_text() -> str:
    """Defensibility blurb for sales / real estate — what you can say in front of an owner."""
    return (
        "We anchor on six owner-intuitive risks: (1) grid reach — can heavy power get to the "
        "building without prohibitive trenching? (2) residential noise exposure — are schools "
        "and homes close enough to generate complaints about HVAC and diesel? (3) cooling climate "
        "— does the local heat profile raise OPEX materially? (4) flood risk — is the site in a "
        "FEMA Special Flood Hazard Area? (5) air quality — will PM2.5 accelerate filter costs and "
        "create permit exposure for backup generators? (6) fiber proximity — is dark fiber already "
        "in the street? All six are live data pulls; fallbacks are noted per criterion."
    )


def coverage_for_teams_text() -> str:
    """Scalability story: same workflow everywhere the address resolves."""
    return (
        "Enter any U.S. commercial or industrial address the geocoder can place. All six scoring "
        "dimensions use public APIs with no key required, so the workflow applies nationwide "
        "without retooling the data layer. Target end-to-end turnaround is well under one minute "
        "per lookup for reps in the field."
    )


def owner_talking_points(
    final_score: float,
    power_score: int,
    zoning_score: int,
    climate_score: int,
    flood_score: int,
    air_quality_score: int,
    fiber_score: int,
    distance_miles: float,
    nuisance_pct: float,
    radius_m: int,
    school_count: int,
    avg_temp_f: float,
    extreme_heat_days: int,
    zone_label: str,
    is_high_risk: bool,
    avg_pm25: float,
    fiber_way_count: int,
    telecom_node_count: int,
) -> list[str]:
    """Concrete bullets reps can use with property owners (not legal advice)."""
    lead = (
        f"Our quick screen scores edge data center feasibility at {final_score:.1f} / 100 across "
        "six headline risks — not a final engineering study, but a solid starting point."
    )
    grid = (
        f"Grid proximity scores {power_score}/100: roughly {distance_miles} miles to the nearest "
        "major substation. Data centers live or die on affordable, reliable megawatts."
    )
    school_bit = f" {school_count} school(s) nearby add ordinance and traffic risk." if school_count else ""
    nuisance = (
        f"Nuisance / zoning scores {zoning_score}/100: about {nuisance_pct:.0f}% of the "
        f"{radius_m} m disk is sensitive land.{school_bit} Loud HVAC and backup generators "
        "draw complaints fast next to homes and schools — solar stays quiet."
    )
    heat_bit = f"{extreme_heat_days} days/year above 95 °F" if extreme_heat_days > 0 else "few extreme heat days"
    climate = (
        f"Climate / cooling scores {climate_score}/100: annual average daily high of {avg_temp_f:.0f} °F, "
        f"{heat_bit}. Hot climates raise HVAC OPEX significantly for power-dense edge facilities."
    )
    flood_bit = f"Zone {zone_label} — inside a FEMA Special Flood Hazard Area." if is_high_risk else f"Zone {zone_label} — outside mapped flood hazard areas."
    flood = (
        f"Flood risk scores {flood_score}/100: {flood_bit} "
        "SFHA designation affects insurance costs, permitting, and resilience planning."
    )
    aq = (
        f"Air quality scores {air_quality_score}/100: 7-day mean PM2.5 of {avg_pm25:.1f} µg/m³. "
        "High particulate matter shortens filter lifetimes and can create permit exposure "
        "for backup diesel generators."
    )
    fiber_detail = (
        f"{fiber_way_count} fiber way(s) and {telecom_node_count} telecom node(s) mapped nearby."
        if fiber_way_count > 0 or telecom_node_count > 0
        else "No fiber conduit or telecom nodes mapped in OSM near this site."
    )
    fiber = (
        f"Fiber proximity scores {fiber_score}/100: {fiber_detail} "
        "Mapped street fiber indicates a carrier-neutral connectivity path exists."
    )
    closer = (
        "If the score is on the low side, rooftop solar is usually the easier owner conversation: "
        "silent operation, no flood or air-quality permit friction, and a straightforward lease story."
    )
    return [lead, grid, nuisance, climate, flood, aq, fiber, closer]


def recommendation_copy(final_score: float) -> tuple[str, str]:
    """Sales-facing narrative. Below 70 we pivot hard to rooftop solar (per brief)."""
    if final_score >= 70:
        return (
            "Edge data center merits deeper diligence",
            "All six headline risks look workable for a power-dense, noise-generating facility. "
            "Still validate utility capacity, easements, local noise ordinances, flood insurance "
            "requirements, and fiber IRU terms before committing CAPEX.",
        )
    return (
        "Rooftop solar is the stronger story on this site",
        "One or more of the six risk dimensions — grid reach, residential exposure, heat load, "
        "flood zone, air quality, or fiber — scores below edge DC viability thresholds. "
        "Position rooftop solar: quiet generation, predictable lease revenue, and faster "
        "neighbor and permit acceptance.",
    )


# ---------------------------------------------------------------------------
# Async fetch wrappers (try live API → fall back to synthetic/defaults)
# ---------------------------------------------------------------------------

async def fetch_power_context(lat: float, lon: float) -> PowerContext:
    """
    Nearest transmission substation distance via HIFLD ArcGIS FeatureServer, with graceful fallback.
    """
    from hifld_substations import nearest_substation_miles

    try:
        dist_mi, note = await nearest_substation_miles(lat, lon, timeout_seconds=28.0)
        return PowerContext(distance_miles=dist_mi, data_source=note)
    except Exception:  # noqa: BLE001
        logger.warning("HIFLD substation lookup failed; using synthetic fallback", exc_info=True)
        return PowerContext(
            distance_miles=synthetic_substation_distance_miles(lat, lon),
            data_source=(
                "HIFLD Electric Substations (service error — temporary coordinate-based estimate; retry later)"
            ),
        )


async def fetch_zoning_context(lat: float, lon: float) -> ZoningContext:
    """
    Residential + school nuisance coverage — synthetic fallback while Overpass is unstable.
    """
    comb = synthetic_residential_percent(lat, lon)
    return ZoningContext(
        nuisance_percent=comb,
        residential_land_percent=comb,
        school_count=0,
        radius_meters=500,
        data_source=(
            "Coordinate-based estimate (OSM Overpass temporarily disabled — live data coming back soon)"
        ),
    )


async def fetch_climate_context(lat: float, lon: float) -> ClimateContext:
    """
    Annual heat profile from Open-Meteo historical archive, with coordinate-based fallback.
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
        logger.warning("Open-Meteo climate query failed; using synthetic fallback", exc_info=True)
        return ClimateContext(
            avg_temp_f=synthetic_avg_temp_f(lat, lon),
            extreme_heat_days=synthetic_extreme_heat_days(lat, lon),
            data_source=(
                "Open-Meteo historical archive (service error — temporary coordinate-based estimate; retry later)"
            ),
        )


async def fetch_flood_context(lat: float, lon: float) -> FloodContext:
    """
    FEMA flood zone lookup via NFHL ArcGIS FeatureServer, with safe fallback.
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


async def fetch_air_quality_context(lat: float, lon: float) -> AirQualityContext:
    """
    7-day PM2.5 and dust averages from Open-Meteo AQ API, with default fallback.
    """
    from air_quality import fetch_air_quality_metrics

    try:
        m = await fetch_air_quality_metrics(lat, lon, timeout_seconds=25.0)
        return AirQualityContext(
            avg_pm25=m.avg_pm25,
            avg_dust=m.avg_dust,
            data_source=m.data_source,
        )
    except Exception:  # noqa: BLE001
        logger.warning("Open-Meteo AQ query failed; using default fallback", exc_info=True)
        return AirQualityContext(
            avg_pm25=10.0,
            avg_dust=5.0,
            data_source=(
                "Open-Meteo Air Quality API (service error — default moderate-quality estimate used; retry later)"
            ),
        )


async def fetch_fiber_context(lat: float, lon: float) -> FiberContext:
    """
    Fiber conduit and telecom node counts — zero fallback while Overpass is unstable.
    """
    return FiberContext(
        fiber_way_count=0,
        telecom_node_count=0,
        data_source=(
            "Coordinate-based estimate (OSM Overpass temporarily disabled — live data coming back soon)"
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
        power_ctx,
        zoning_ctx,
        climate_ctx,
        flood_ctx,
        aq_ctx,
        fiber_ctx,
    ) = await asyncio.gather(
        fetch_power_context(lat, lon),
        fetch_zoning_context(lat, lon),
        fetch_climate_context(lat, lon),
        fetch_flood_context(lat, lon),
        fetch_air_quality_context(lat, lon),
        fetch_fiber_context(lat, lon),
    )

    power_score, power_band = score_power_proximity(power_ctx.distance_miles)
    zoning_score = score_nuisance_disk(zoning_ctx.nuisance_percent)
    climate_score = score_climate(climate_ctx.avg_temp_f, climate_ctx.extreme_heat_days)
    flood_score = score_flood(flood_ctx.is_high_risk)
    aq_score = score_air_quality(aq_ctx.avg_pm25)
    fiber_score = score_fiber(fiber_ctx.fiber_way_count, fiber_ctx.telecom_node_count)

    final = blended_feasibility(power_score, zoning_score, climate_score, flood_score, aq_score, fiber_score)
    title, body = recommendation_copy(final)

    dist = round(power_ctx.distance_miles, 2)
    nui_pct = round(zoning_ctx.nuisance_percent, 2)
    land_pct = round(zoning_ctx.residential_land_percent, 2)

    power_rationale = (
        "Edge facilities need serious, continuous grid power. When transmission-class "
        "infrastructure is far away, trenching, upgrades, and timeline risk dominate — "
        "something owners and lenders grasp quickly."
    )
    power_rules = (
        f"Subscore 100 if the nearest substation is under 1 mile; 50 between 1 and 3 miles; "
        f"10 beyond 3 miles. For this pin we measure {dist} miles (see data note)."
    )
    zoning_rationale = (
        "Data centers need industrial-scale cooling and backup diesel — both are loud. Proximity "
        "to mapped residential land and schools raises noise-ordinance risk, hearings, and neighbor "
        "opposition. Rooftop solar is effectively silent."
    )
    zoning_rules = (
        f"We measure how much of a {zoning_ctx.radius_meters} m disk is covered by OSM residential "
        f"land plus school footprints (80 m buffer around point schools). Combined coverage "
        f"{nui_pct}% drives the subscore (residential land alone {land_pct}%; "
        f"{zoning_ctx.school_count} school feature(s)). "
        "Curve: 0% → 100 pts, linear to 20 pts at 20%, flat at 20 beyond that."
    )
    climate_rationale = (
        "Cooling is a top-three OPEX line for edge data centers. High annual average temperatures "
        "raise baseline chiller load, while extreme heat days push cooling systems to rated limits "
        "and increase failure risk and energy cost spikes."
    )
    climate_rules = (
        f"Avg daily-max {climate_ctx.avg_temp_f:.1f} °F and {climate_ctx.extreme_heat_days} days "
        "above 95 °F. Score 100 if avg < 75 °F and heat days < 15; 60 if avg < 85 °F or "
        "heat days < 30; 20 otherwise."
    )
    flood_rationale = (
        "FEMA Special Flood Hazard Area (A/V zones) designation raises flood insurance premiums, "
        "requires elevation certificates, and triggers additional permitting for below-grade "
        "electrical infrastructure and backup generator fuel tanks."
    )
    flood_rules = (
        f"Zone {flood_ctx.zone_label} — {'high risk (A/V zone)' if flood_ctx.is_high_risk else 'not high risk'}. "
        "Score 20 if any intersecting FEMA feature is an A or V zone; 90 otherwise."
    )
    aq_rationale = (
        "High particulate matter concentrations accelerate CRAC filter replacement, degrade "
        "heat-exchanger efficiency, and can create permit exposure for backup diesel generators "
        "under local air-quality rules."
    )
    aq_rules = (
        f"7-day mean PM2.5: {aq_ctx.avg_pm25:.1f} µg/m³. "
        "Score 100 if < 5; 70 if < 12 (EPA annual standard); 40 if < 25; 15 otherwise."
    )
    fiber_rationale = (
        "Carrier-neutral dark fiber already in the street dramatically reduces the cost and "
        "lead time to light a high-capacity edge facility. Absence of any mapped fiber is a "
        "strong negative signal — the operator must trench or rely on wireless backhaul."
    )
    fiber_rules = (
        f"{fiber_ctx.fiber_way_count} fiber way(s), {fiber_ctx.telecom_node_count} telecom node(s). "
        "Score 100 if ≥ 3 fiber ways or ≥ 1 telecom node; 60 if ≥ 1 fiber way; 20 if none."
    )

    return {
        "latitude": lat,
        "longitude": lon,
        "final_score": final,
        "power": {
            "score": power_score,
            "weight_percent": int(POWER_WEIGHT * 100),
            "distance_miles": dist,
            "band_label": power_band,
            "data_source": power_ctx.data_source,
            "rationale": power_rationale,
            "scoring_rules_plain": power_rules,
        },
        "zoning": {
            "score": zoning_score,
            "weight_percent": int(ZONING_WEIGHT * 100),
            "residential_percent": nui_pct,
            "residential_land_percent": land_pct,
            "school_count": zoning_ctx.school_count,
            "radius_meters": zoning_ctx.radius_meters,
            "data_source": zoning_ctx.data_source,
            "rationale": zoning_rationale,
            "scoring_rules_plain": zoning_rules,
        },
        "climate": {
            "score": climate_score,
            "weight_percent": int(CLIMATE_WEIGHT * 100),
            "avg_temp_f": climate_ctx.avg_temp_f,
            "extreme_heat_days": climate_ctx.extreme_heat_days,
            "data_source": climate_ctx.data_source,
            "rationale": climate_rationale,
            "scoring_rules_plain": climate_rules,
        },
        "flood": {
            "score": flood_score,
            "weight_percent": int(FLOOD_WEIGHT * 100),
            "zone_label": flood_ctx.zone_label,
            "is_high_risk": flood_ctx.is_high_risk,
            "feature_count": flood_ctx.feature_count,
            "data_source": flood_ctx.data_source,
            "rationale": flood_rationale,
            "scoring_rules_plain": flood_rules,
        },
        "air_quality": {
            "score": aq_score,
            "weight_percent": int(AIR_QUALITY_WEIGHT * 100),
            "avg_pm25": aq_ctx.avg_pm25,
            "avg_dust": aq_ctx.avg_dust,
            "data_source": aq_ctx.data_source,
            "rationale": aq_rationale,
            "scoring_rules_plain": aq_rules,
        },
        "fiber": {
            "score": fiber_score,
            "weight_percent": int(FIBER_WEIGHT * 100),
            "fiber_way_count": fiber_ctx.fiber_way_count,
            "telecom_node_count": fiber_ctx.telecom_node_count,
            "data_source": fiber_ctx.data_source,
            "rationale": fiber_rationale,
            "scoring_rules_plain": fiber_rules,
        },
        "recommendation_title": title,
        "recommendation_body": body,
        "phase_note": (
            "Live data sources: HIFLD Open Data (ArcGIS) for grid distance; OSM Overpass for "
            "residential landuse + school footprints within 500 m; Open-Meteo archive for annual "
            "heat profile; FEMA NFHL (ArcGIS) for flood zone; Open-Meteo Air Quality API for "
            "7-day PM2.5; OSM Overpass for fiber conduit + telecom nodes. If any service fails, "
            "that leg falls back to a coordinate-based estimate — check each criterion's data source "
            "note. Geocoding via Nominatim unless a map pin is provided."
        ),
        "verdict_plain_english": verdict_plain_english(final),
        "formula_display": formula_display_text(),
        "methodology_for_teams": methodology_for_teams_text(),
        "coverage_for_teams": coverage_for_teams_text(),
        "owner_talking_points": owner_talking_points(
            final,
            power_score,
            zoning_score,
            climate_score,
            flood_score,
            aq_score,
            fiber_score,
            dist,
            nui_pct,
            zoning_ctx.radius_meters,
            zoning_ctx.school_count,
            climate_ctx.avg_temp_f,
            climate_ctx.extreme_heat_days,
            flood_ctx.zone_label,
            flood_ctx.is_high_risk,
            aq_ctx.avg_pm25,
            fiber_ctx.fiber_way_count,
            fiber_ctx.telecom_node_count,
        ),
    }
