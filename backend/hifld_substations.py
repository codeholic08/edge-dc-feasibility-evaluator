"""
Nearest HIFLD electric substation (great-circle miles) via ArcGIS FeatureServer.

Dataset: Homeland Infrastructure Foundation-Level Data (HIFLD) — transmission-class substations
exposed on ArcGIS Online (public Query endpoint, no API key).

We request substations within a large search radius around the pin, then compute the true
haversine distance to the closest facility in that candidate set.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Public FeatureServer (layer 0 = point features with LATITUDE / LONGITUDE attributes).
HIFLD_QUERY_URL = (
    "https://services5.arcgis.com/HDRa0B57OVrv2E1q/arcgis/rest/services/"
    "Electric_Substations/FeatureServer/0/query"
)

# First pass: ~100 mi — enough for urban CONUS; widen if the service returns nothing.
SEARCH_RADIUS_METERS_INITIAL = 160_934
SEARCH_RADIUS_METERS_WIDE = 804_672  # ~500 mi

EARTH_RADIUS_MILES = 3958.7613


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in statute miles (WGS84 sphere approximation)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(h)))


def _coords_from_feature(feat: dict[str, Any]) -> tuple[float, float] | None:
    """Extract (lat, lon) from ArcGIS JSON feature."""
    geom = feat.get("geometry") or {}
    if "y" in geom and "x" in geom:
        return float(geom["y"]), float(geom["x"])
    attrs = feat.get("attributes") or {}
    lat, lon = attrs.get("LATITUDE"), attrs.get("LONGITUDE")
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    return None


async def nearest_substation_miles(
    lat: float,
    lon: float,
    *,
    timeout_seconds: float = 28.0,
) -> tuple[float, str]:
    """
    Return (distance_miles, short_provenance_note).

    Raises:
        RuntimeError: if no substation could be resolved after widening the search.
    """
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        for radius_m, label in (
            (SEARCH_RADIUS_METERS_INITIAL, "100 mi search"),
            (SEARCH_RADIUS_METERS_WIDE, "500 mi search"),
        ):
            payload = {
                "f": "json",
                "where": "1=1",
                "geometry": json.dumps({"x": lon, "y": lat}),
                "geometryType": "esriGeometryPoint",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "distance": str(radius_m),
                "units": "esriSRUnit_Meter",
                "returnGeometry": "true",
                "outFields": "LATITUDE,LONGITUDE,NAME,OBJECTID_1",
                "resultRecordCount": "2000",
            }
            response = await client.post(HIFLD_QUERY_URL, data=payload)
            response.raise_for_status()
            data = response.json()
            if data.get("error"):
                err = data["error"]
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                raise RuntimeError(f"HIFLD ArcGIS error: {msg}")
            feats = data.get("features") or []
            if not feats:
                logger.info("HIFLD query returned 0 features (%s, radius=%s m)", label, radius_m)
                continue

            best_mi: float | None = None
            for feat in feats:
                pair = _coords_from_feature(feat)
                if pair is None:
                    continue
                slat, slon = pair
                mi = _haversine_miles(lat, lon, slat, slon)
                if best_mi is None or mi < best_mi:
                    best_mi = mi

            if best_mi is not None:
                note = (
                    f"HIFLD Open Data / ArcGIS FeatureServer; nearest of {len(feats)} candidates "
                    f"within {label}"
                )
                return round(best_mi, 2), note

    raise RuntimeError("HIFLD returned no substation features near this pin")
