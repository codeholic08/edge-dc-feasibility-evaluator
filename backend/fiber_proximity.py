"""
Fiber / telecom infrastructure proximity via OSM Overpass.

Queries two feature classes near the pin:
  - Fiber conduit ways (communication:fibre=yes, communication:fibre_optic=yes,
    or man_made=cable) within 1000 m — physical dark-fiber in street or utility easement.
  - Telecom anchor nodes (telecom=data_center, internet_access=yes) within 500 m —
    co-location facilities and known connectivity POPs.

Dense street-level fiber and adjacent data-center infrastructure substantially lower
dark-fiber lease costs and shorten the path to carrier-neutral connectivity for an edge
facility. Complete absence of mapped fiber is a strong negative signal in rural or
under-mapped suburban areas.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from overpass_client import overpass_post

logger = logging.getLogger(__name__)

FIBER_RADIUS_M = 1000
TELECOM_RADIUS_M = 500


@dataclass(frozen=True)
class FiberMetrics:
    """OSM-derived fiber conduit and telecom infrastructure counts near the pin."""

    fiber_way_count: int
    telecom_node_count: int
    data_source: str


async def fetch_fiber_metrics(
    lat: float,
    lon: float,
    *,
    timeout_seconds: float = 40.0,
) -> FiberMetrics:
    """
    Two Overpass queries: fiber conduit ways (1000 m radius) and telecom nodes (500 m radius).

    Uses ``out ids;`` for efficient ID-only responses; deduplication is handled by the
    Overpass union operator.

    Raises:
        RuntimeError: if Overpass returns an HTTP error on either query.
    """
    ql_timeout = int(timeout_seconds)
    http_timeout = timeout_seconds + 8.0

    q_fiber = f"""
    [out:json][timeout:{ql_timeout}];
    (
      way["communication:fibre"="yes"](around:{FIBER_RADIUS_M},{lat},{lon});
      way["communication:fibre_optic"="yes"](around:{FIBER_RADIUS_M},{lat},{lon});
      way["man_made"="cable"](around:{FIBER_RADIUS_M},{lat},{lon});
    );
    out ids;
    """

    q_telecom = f"""
    [out:json][timeout:{ql_timeout}];
    (
      node["telecom"="data_center"](around:{TELECOM_RADIUS_M},{lat},{lon});
      node["internet_access"="yes"](around:{TELECOM_RADIUS_M},{lat},{lon});
    );
    out ids;
    """

    async with httpx.AsyncClient(timeout=http_timeout) as client:
        fiber_data = await overpass_post(q_fiber, client=client, label="fiber/ways")
        fiber_elements = fiber_data.get("elements") or []

        telecom_data = await overpass_post(q_telecom, client=client, label="fiber/telecom-nodes")
        telecom_elements = telecom_data.get("elements") or []

    fiber_count = len(fiber_elements)
    telecom_count = len(telecom_elements)

    note = (
        f"OSM Overpass: fiber ways (communication:fibre/fibre_optic, man_made=cable) "
        f"within {FIBER_RADIUS_M} m — {fiber_count} feature(s); "
        f"telecom nodes (telecom=data_center, internet_access=yes) "
        f"within {TELECOM_RADIUS_M} m — {telecom_count} feature(s)"
    )
    return FiberMetrics(
        fiber_way_count=fiber_count,
        telecom_node_count=telecom_count,
        data_source=note,
    )
