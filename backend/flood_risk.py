"""
FEMA flood zone lookup via the National Flood Hazard Layer (NFHL) ArcGIS FeatureServer.

Queries flood-zone polygons within 200 m of the pin from FEMA's public MapServer (layer 28).
FEMA flood zone designations:
  - A* zones (A, AE, AH, AO, AR, A99): Special Flood Hazard Area (100-year flood)
  - V* zones (V, VE): Coastal high-hazard / wave action zone
  - X (shaded): 500-year flood / moderate risk
  - X (unshaded), D: Minimal or undetermined risk

is_high_risk = True when any intersecting feature carries an A or V zone prefix, indicating
that the site falls inside FEMA's Special Flood Hazard Area — a material concern for
infrastructure permitting, insurance, and resilience planning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

NFHL_QUERY_URL = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
)

SEARCH_RADIUS_METERS = 200


@dataclass(frozen=True)
class FloodMetrics:
    """FEMA flood zone classification at the analysis pin."""

    zone_label: str
    is_high_risk: bool
    feature_count: int
    data_source: str


async def fetch_flood_metrics(
    lat: float,
    lon: float,
    *,
    timeout_seconds: float = 25.0,
) -> FloodMetrics:
    """
    Query FEMA NFHL MapServer layer 28 (flood hazard areas) within 200 m of the pin.

    Returns the most restrictive zone label found (V > A > X > D precedence).
    Raises:
        RuntimeError: if the ArcGIS service returns an error payload.
    """
    payload = {
        "f": "json",
        "where": "1=1",
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": str(SEARCH_RADIUS_METERS),
        "units": "esriSRUnit_Meter",
        "outFields": "FLD_ZONE,ZONE_SUBTY,DFIRM_ID",
        "returnGeometry": "false",
        "resultRecordCount": "100",
    }

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(NFHL_QUERY_URL, data=payload)
    response.raise_for_status()
    data = response.json()

    if data.get("error"):
        err = data["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise RuntimeError(f"FEMA NFHL ArcGIS error: {msg}")

    features = data.get("features") or []
    if not features:
        note = (
            f"FEMA NFHL MapServer layer 28; 0 flood zone features within {SEARCH_RADIUS_METERS} m — "
            "site appears outside mapped flood zones (treated as Zone X / minimal risk)"
        )
        return FloodMetrics(zone_label="X", is_high_risk=False, feature_count=0, data_source=note)

    zones: list[str] = []
    for feat in features:
        attrs = feat.get("attributes") or {}
        zone = attrs.get("FLD_ZONE")
        if zone:
            zones.append(str(zone).strip().upper())

    is_high_risk = any(z.startswith(("A", "V")) for z in zones)

    # Return the most restrictive label for display
    if any(z.startswith("V") for z in zones):
        label = next(z for z in zones if z.startswith("V"))
    elif any(z.startswith("A") for z in zones):
        label = next(z for z in zones if z.startswith("A"))
    elif zones:
        label = zones[0]
    else:
        label = "X"

    unique_zones = ", ".join(sorted(set(zones)))
    note = (
        f"FEMA National Flood Hazard Layer (NFHL) MapServer layer 28; "
        f"{len(features)} feature(s) within {SEARCH_RADIUS_METERS} m; "
        f"zones: {unique_zones}"
    )
    return FloodMetrics(
        zone_label=label,
        is_high_risk=is_high_risk,
        feature_count=len(features),
        data_source=note,
    )
