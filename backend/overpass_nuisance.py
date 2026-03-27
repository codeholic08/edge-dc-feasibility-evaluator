"""
Nuisance / sensitive-receptor context within a fixed-radius disk (OSM + Overpass).

Combines:
  - ``landuse=residential`` polygons (area overlap with the disk), and
  - ``amenity=school`` nodes and ways, modeled as footprint intersection or a fixed buffer around
    point schools (proxy for playgrounds, pickup noise, and zoning scrutiny).

The **combined** share of the analysis disk covered by this union drives the 40% weighted
“nuisance” subscore — aligned with sales messaging on noise ordinances vs. silent rooftop solar.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Set, Tuple

import httpx
from pyproj import CRS, Transformer
from shapely.geometry import Point, Polygon
from shapely.ops import transform, unary_union

from overpass_client import overpass_post

logger = logging.getLogger(__name__)

# Point schools (and way centroids without geometry) get a notional “sensitive receptor” zone.
DEFAULT_SCHOOL_BUFFER_M = 80.0


def _utm_epsg(lat: float, lon: float) -> int:
    zone = int((lon + 180) / 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def _disk_and_transformers(lat: float, lon: float, radius_m: float):
    epsg = _utm_epsg(lat, lon)
    crs = CRS.from_epsg(epsg)
    to_utm = Transformer.from_crs(CRS.from_epsg(4326), crs, always_xy=True)
    to_wgs = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)
    center_utm = transform(to_utm.transform, Point(lon, lat))
    disk = center_utm.buffer(radius_m)
    disk_area_m2 = math.pi * radius_m**2
    return disk, disk_area_m2, to_utm, to_wgs


def _residential_polygons(elements: list[dict[str, Any]]) -> list[Polygon]:
    polys: list[Polygon] = []
    for el in elements:
        if el.get("type") != "way":
            continue
        if (el.get("tags") or {}).get("landuse") != "residential":
            continue
        geom = el.get("geometry")
        if not geom:
            continue
        coords = [(pt["lon"], pt["lat"]) for pt in geom if "lon" in pt and "lat" in pt]
        if len(coords) < 3:
            continue
        try:
            p = Polygon(coords)
            if p.is_valid and p.area > 0:
                polys.append(p)
        except Exception:  # noqa: BLE001
            continue
    return polys


def _school_footprints(
    elements: list[dict[str, Any]],
    to_utm,
    disk,
    school_buffer_m: float,
) -> tuple[list, int]:
    """
    Build metric geometries for schools intersecting the disk: polygon clips or buffered points.
    Returns (intersection pieces in UTM, count of distinct OSM school features).
    """
    pieces: list = []
    seen: Set[Tuple[str, int]] = set()
    for el in elements:
        if (el.get("tags") or {}).get("amenity") != "school":
            continue
        eid = el.get("id")
        et = el.get("type")
        if eid is None or et not in ("node", "way"):
            continue
        seen.add((et, int(eid)))

        if et == "node":
            lat, lon = el.get("lat"), el.get("lon")
            if (lat is None or lon is None) and el.get("geometry"):
                g0 = el["geometry"][0]
                lat, lon = g0.get("lat"), g0.get("lon")
            if lat is None or lon is None:
                continue
            try:
                pt = transform(to_utm.transform, Point(float(lon), float(lat)))
                zone = pt.buffer(school_buffer_m).intersection(disk)
                if zone.area > 0:
                    pieces.append(zone)
            except Exception as exc:  # noqa: BLE001
                logger.debug("school node skip: %s", exc)
        elif et == "way":
            geom = el.get("geometry")
            if not geom:
                continue
            coords = [(pt["lon"], pt["lat"]) for pt in geom if "lon" in pt and "lat" in pt]
            if len(coords) < 3:
                continue
            try:
                poly_ll = Polygon(coords)
                if not poly_ll.is_valid:
                    poly_ll = poly_ll.buffer(0)
                poly_utm = transform(to_utm.transform, poly_ll)
                inter = disk.intersection(poly_utm)
                if inter.area > 0:
                    pieces.append(inter)
            except Exception as exc:  # noqa: BLE001
                logger.debug("school way skip: %s", exc)
    return pieces, len(seen)


def _pct_of_disk(pieces: list, disk, disk_area_m2: float) -> float:
    if not pieces or disk_area_m2 <= 0:
        return 0.0
    covered = unary_union(pieces).area
    return max(0.0, min(100.0, round((covered / disk_area_m2) * 100.0, 2)))


@dataclass(frozen=True)
class NuisanceDiskMetrics:
    """Transparent inputs for the zoning / nuisance subscore."""

    residential_land_percent: float
    school_count: int
    combined_nuisance_percent: float
    radius_meters: int
    note: str


async def fetch_nuisance_disk_metrics(
    lat: float,
    lon: float,
    *,
    radius_meters: int = 500,
    school_buffer_meters: float = DEFAULT_SCHOOL_BUFFER_M,
    timeout_seconds: float = 50.0,
) -> NuisanceDiskMetrics:
    """
    Two Overpass round-trips (residential ways, then schools) to stay under parser complexity limits.
    """
    timeout = timeout_seconds + 8.0

    q_res = f"""
    [out:json][timeout:{int(timeout_seconds)}];
    way["landuse"="residential"](around:{radius_meters},{lat},{lon});
    out geom;
    """
    q_school = f"""
    [out:json][timeout:{int(timeout_seconds)}];
    (
      node["amenity"="school"](around:{radius_meters},{lat},{lon});
      way["amenity"="school"](around:{radius_meters},{lat},{lon});
    );
    out geom;
    """

    async with httpx.AsyncClient(timeout=timeout) as client:
        res_data = await overpass_post(q_res, client=client, label="nuisance/residential")
        res_elements = res_data.get("elements") or []

        school_data = await overpass_post(q_school, client=client, label="nuisance/schools")
        school_elements = school_data.get("elements") or []

    disk, disk_area_m2, to_utm, _ = _disk_and_transformers(lat, lon, float(radius_meters))

    res_polys = _residential_polygons(res_elements)
    res_pieces: list = []
    for poly_ll in res_polys:
        try:
            pu = transform(to_utm.transform, poly_ll)
            if not pu.is_valid:
                pu = pu.buffer(0)
            inter = disk.intersection(pu)
            if inter.area > 0:
                res_pieces.append(inter)
        except Exception as exc:  # noqa: BLE001
            logger.debug("residential intersection skip: %s", exc)

    residential_only_pct = _pct_of_disk(res_pieces, disk, disk_area_m2)

    school_pieces, school_count = _school_footprints(
        school_elements, to_utm, disk, school_buffer_meters
    )

    all_pieces = res_pieces + school_pieces
    combined_pct = _pct_of_disk(all_pieces, disk, disk_area_m2)

    note = (
        f"OSM Overpass: {radius_meters} m disk — residential land {residential_only_pct:.2f}% of disk, "
        f"{school_count} school feature(s) (80 m buffer on point schools); combined sensitive coverage "
        f"{combined_pct:.2f}%"
    )

    return NuisanceDiskMetrics(
        residential_land_percent=residential_only_pct,
        school_count=school_count,
        combined_nuisance_percent=combined_pct,
        radius_meters=radius_meters,
        note=note,
    )
