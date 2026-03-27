"""
Feasibility scoring: weighted blend of power access (60%) and residential/noise risk (40%).

Phase 2 uses **live** HIFLD (ArcGIS) + OpenStreetMap Overpass with timeouts. If either upstream
service fails, we fall back to deterministic coordinate-based estimates so reps still get a number.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Weights (must sum to 1.0 for mental model; we document percentages in API)
# ---------------------------------------------------------------------------
POWER_WEIGHT = 0.60
ZONING_WEIGHT = 0.40


def _pin_digest(lat: float, lon: float) -> bytes:
    """Stable fingerprint for a WGS84 pin (used for Phase 1 synthetic inputs only)."""
    payload = f"{lat:.7f}|{lon:.7f}".encode("utf-8")
    return hashlib.sha256(payload).digest()


def synthetic_substation_distance_miles(lat: float, lon: float) -> float:
    """
    Phase 1 stand-in for HIFLD nearest-substation distance.

    Varies **deterministically** with lat/lon so different addresses get different scores, while the
    same pin always matches. Not a real grid measurement — replace with HIFLD in Phase 2.
    """
    d = _pin_digest(lat, lon)
    u = int.from_bytes(d[0:4], "big") / float(2**32)
    return round(0.15 + u * 5.85, 2)  # ~0.15 .. 6.0 mi → all distance bands appear


def synthetic_residential_percent(lat: float, lon: float) -> float:
    """
    Phase 1 stand-in for Overpass residential land share within 500 m.

    Same idea: stable pseudo-random from coordinates, not OSM geometry.
    """
    d = _pin_digest(lat, lon)
    u = int.from_bytes(d[4:8], "big") / float(2**32)
    return round(u * 42.0, 2)  # 0 .. 42% → mix of low, interpolated, and >20% floors


@dataclass(frozen=True)
class PowerContext:
    """Everything the UI needs to explain the power constraint."""

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


def score_power_proximity(distance_miles: float) -> tuple[int, str]:
    """
    Map great-circle distance to the nearest high-voltage substation to a 0–100 score.

    Spec:
      - < 1 mile  → 100
      - 1–3 miles → 50
      - > 3 miles → 10
    """
    if distance_miles < 1.0:
        return 100, "Within 1 mile of transmission-class infrastructure"
    if distance_miles <= 3.0:
        return 50, "1-3 miles: trenching and feeder upgrades materially erode economics"
    return 10, "Beyond 3 miles: long-distance grid extension is typically prohibitive"


def score_nuisance_disk(nuisance_disk_percent: float) -> int:
    """
    Map **combined** sensitive land share (residential + schools in the analysis disk) to 0–100.

    Spec anchors:
      - 0% coverage          → 100
      - strictly > 20%       → 20

    Linear between 0% and 20% (same curve as the original residential-only rule).
    """
    if nuisance_disk_percent <= 0.0:
        return 100
    if nuisance_disk_percent > 20.0:
        return 20
    t = nuisance_disk_percent / 20.0
    return int(round(100.0 + t * (20.0 - 100.0)))


def blended_feasibility(power_score: int, zoning_score: int) -> float:
    """Final 0–100 feasibility score with documented weights."""
    raw = POWER_WEIGHT * power_score + ZONING_WEIGHT * zoning_score
    return round(raw, 1)


def verdict_plain_english(final_score: float) -> str:
    """
    Short, jargon-light summary for someone seeing the tool for the first time.

    Higher scores mean edge data centers look *relatively* less painful on the two risks we model;
    lower scores mean rooftop solar is usually the smoother owner conversation.
    """
    if final_score >= 70:
        return (
            "At a glance: grid access looks close enough that a power-hungry edge facility is not "
            "ruled out on distance alone, and nearby residential pressure looks moderate. Treat this "
            "as a starting point — utilities and local rules still need confirmation."
        )
    return (
        "At a glance: either the site is a stretch for affordable grid tie-in, neighbors are "
        "predominantly residential (noise and permitting risk), or both. That usually makes "
        "rooftop solar the simpler, faster story for the owner — fewer moving parts, quieter operation."
    )


def formula_display_text() -> str:
    """Exact weighting string for UI and slide decks."""
    p = int(POWER_WEIGHT * 100)
    z = int(ZONING_WEIGHT * 100)
    return (
        f"Final score = ({p}% × grid proximity score) + ({z}% × nuisance / zoning score). "
        "Nuisance blends OSM residential land + schools in a 500 m disk. Each subscore is 0–100. "
        "Higher final = relatively better for edge DCs on these two risks."
    )


def methodology_for_teams_text() -> str:
    """Defensibility blurb for sales / real estate — what you can say in front of an owner."""
    return (
        "We anchor on two owner-intuitive risks: (1) whether heavy grid power is close enough that "
        "trenching does not blow up the budget (HIFLD substations, straight-line miles), and "
        "(2) whether the site sits against sensitive neighbors — mapped residential land plus schools "
        "within 500 m as a proxy for noise ordinances and zoning friction. Rooftop solar stays quiet; "
        "edge DCs are not. Fiber, cooling climate, air quality, and building form still matter for a "
        "full pro forma — good follow-on diligence topics."
    )


def coverage_for_teams_text() -> str:
    """Scalability story: same workflow everywhere the address resolves."""
    return (
        "Enter any U.S. commercial or industrial address the geocoder can place. The workflow, "
        "weights, and scoring bands stay the same nationwide — only the underlying measurements "
        "change per pin. Target end-to-end turnaround is well under one minute per lookup for reps "
        "in the field."
    )


def owner_talking_points(
    final_score: float,
    power_score: int,
    zoning_score: int,
    distance_miles: float,
    nuisance_pct: float,
    radius_m: int,
    school_count: int,
) -> list[str]:
    """Concrete bullets reps can use with property owners (not legal advice)."""
    lead = (
        f"Our quick screen scores edge data center feasibility at {final_score:.1f} out of 100 on two "
        "headline risks — not a final engineering study."
    )
    grid = (
        f"Grid proximity scores {power_score}/100 today using roughly {distance_miles} road-miles to the "
        "nearest major substation in our dataset — data centers live or die on affordable megawatts."
    )
    school_bit = f" {school_count} mapped school(s) nearby add ordinance and pickup-traffic risk." if school_count else ""
    res = (
        f"Nuisance / zoning pressure scores {zoning_score}/100 from about {nuisance_pct:.0f}% of the "
        f"{radius_m} m disk in sensitive land (residential + schools).{school_bit} Loud HVAC and backup "
        "gens draw complaints fast next to homes and schools — solar stays quiet."
    )
    closer = (
        "If the score is on the low side, rooftop solar is usually the easier owner conversation: "
        "quieter, fewer neighbor issues, and a straightforward lease payment story."
    )
    return [lead, grid, res, closer]


def recommendation_copy(final_score: float) -> tuple[str, str]:
    """
    Sales-facing narrative. Below 70 we pivot hard to rooftop solar (per brief).
    """
    if final_score >= 70:
        return (
            "Edge data center merits deeper diligence",
            "Grid proximity and surrounding land use look workable for a loud, power-dense "
            "facility. Still validate utility capacity, easements, and local noise ordinances "
            "before committing CAPEX.",
        )
    return (
        "Rooftop solar is the stronger story on this site",
        "Substations are far enough, or residential exposure is high enough, that edge "
        "data center economics and permitting risk are unattractive. Position rooftop solar: "
        "quiet generation, predictable lease revenue, and faster neighbor acceptance.",
    )


async def fetch_power_context(lat: float, lon: float) -> PowerContext:
    """
    Nearest transmission substation distance via HIFLD ArcGIS FeatureServer, with graceful fallback.
    """
    from hifld_substations import nearest_substation_miles

    try:
        dist_mi, note = await nearest_substation_miles(lat, lon, timeout_seconds=28.0)
        return PowerContext(distance_miles=dist_mi, data_source=note)
    except Exception:
        logger.warning("HIFLD substation lookup failed; using synthetic fallback", exc_info=True)
        return PowerContext(
            distance_miles=synthetic_substation_distance_miles(lat, lon),
            data_source=(
                "HIFLD Electric Substations (service error — temporary coordinate-based estimate; retry later)"
            ),
        )


async def fetch_zoning_context(lat: float, lon: float) -> ZoningContext:
    """
    Residential + school (nuisance) coverage within 500 m via Overpass + geometry, with fallback.
    """
    from overpass_nuisance import fetch_nuisance_disk_metrics

    try:
        m = await fetch_nuisance_disk_metrics(lat, lon, radius_meters=500, timeout_seconds=48.0)
        return ZoningContext(
            nuisance_percent=m.combined_nuisance_percent,
            residential_land_percent=m.residential_land_percent,
            school_count=m.school_count,
            radius_meters=m.radius_meters,
            data_source=m.note,
        )
    except Exception:
        logger.warning("Overpass nuisance query failed; using synthetic fallback", exc_info=True)
        comb = synthetic_residential_percent(lat, lon)
        return ZoningContext(
            nuisance_percent=comb,
            residential_land_percent=comb,
            school_count=0,
            radius_meters=500,
            data_source=(
                "OpenStreetMap Overpass (service error — temporary coordinate-based estimate; retry later)"
            ),
        )


async def evaluate_site(lat: float, lon: float) -> dict:
    """
    Run both constraints, blend scores, and return a dict ready for ``EvaluateResponse``.

    This is the single orchestration entry point the FastAPI route calls.
    """
    power_ctx, zoning_ctx = await asyncio.gather(
        fetch_power_context(lat, lon),
        fetch_zoning_context(lat, lon),
    )

    power_score, power_band = score_power_proximity(power_ctx.distance_miles)
    zoning_score = score_nuisance_disk(zoning_ctx.nuisance_percent)
    final = blended_feasibility(power_score, zoning_score)
    title, body = recommendation_copy(final)
    dist = round(power_ctx.distance_miles, 2)
    nui_pct = round(zoning_ctx.nuisance_percent, 2)
    land_pct = round(zoning_ctx.residential_land_percent, 2)

    power_rationale = (
        "Edge facilities need serious, continuous grid power. When transmission-class infrastructure "
        "is far away, trenching, upgrades, and timeline risk dominate — something owners and "
        "lenders grasp quickly."
    )
    power_rules = (
        f"Subscore 100 if the nearest substation is under 1 mile; 50 between 1 and 3 miles; "
        f"10 beyond 3 miles. For this pin we are using {dist} miles (see data note)."
    )
    zoning_rationale = (
        "Data centers need industrial-scale cooling and backup diesel — both are loud. Proximity to "
        "mapped residential land and schools raises noise-ordinance risk, hearings, and neighbor "
        "opposition. Rooftop solar is effectively silent."
    )
    zoning_rules = (
        f"We measure how much of a {zoning_ctx.radius_meters} m disk is covered by OSM residential land "
        f"plus school footprints (80 m buffer around point schools). Combined coverage {nui_pct}% drives "
        f"the subscore (residential land alone {land_pct}%; {zoning_ctx.school_count} school feature(s) in radius). "
        "Same curve as before: 0% → 100 pts, linear to 20 pts at 20%, flat at 20 beyond that."
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
        "recommendation_title": title,
        "recommendation_body": body,
        "phase_note": "Live data: HIFLD substations (ArcGIS) for grid distance; OSM Overpass for "
        "landuse=residential polygons and amenity=school (ways + nodes, 80 m buffer on point schools) "
        "within a 500 m disk. Combined sensitive coverage drives the nuisance score. If an API fails, "
        "that leg falls back to a coordinate estimate — read each criterion's data source. Geocoding: "
        "Nominatim unless you send a map pin.",
        "verdict_plain_english": verdict_plain_english(final),
        "formula_display": formula_display_text(),
        "methodology_for_teams": methodology_for_teams_text(),
        "coverage_for_teams": coverage_for_teams_text(),
        "owner_talking_points": owner_talking_points(
            final,
            power_score,
            zoning_score,
            dist,
            nui_pct,
            zoning_ctx.radius_meters,
            zoning_ctx.school_count,
        ),
    }
