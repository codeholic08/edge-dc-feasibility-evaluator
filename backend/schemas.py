"""
Pydantic models for the public HTTP API.

These shapes mirror what the Next.js dashboard consumes so the contract stays obvious
during Phase 1 (mocked data) and Phase 2 (live HIFLD / Overpass).
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class EvaluateRequest(BaseModel):
    """
    Either a geocodable **address** (≥3 chars) **or** both **latitude** and **longitude** (map pin).

    When coordinates are sent, geocoding is skipped; empty address is allowed and the API substitutes
    a display label for the response.
    """

    address: str = Field(default="", max_length=500, description="Free-form address; optional if lat/lon are sent")
    latitude: Optional[float] = Field(None, ge=-90, le=90, description="Optional; must pair with longitude")
    longitude: Optional[float] = Field(None, ge=-180, le=180, description="Optional; must pair with latitude")

    @model_validator(mode="after")
    def address_or_map_pin(self) -> "EvaluateRequest":
        lat, lon = self.latitude, self.longitude
        if (lat is None) ^ (lon is None):
            raise ValueError("latitude and longitude must both be set together, or both omitted")
        stripped = (self.address or "").strip()
        has_pin = lat is not None and lon is not None
        if not has_pin and len(stripped) < 3:
            raise ValueError("Enter an address (at least 3 characters) or drop a pin on the map.")
        return self.model_copy(update={"address": stripped})


class PowerBreakdown(BaseModel):
    """
    Constraint 1 — proximity to high-voltage infrastructure (HIFLD substations in Phase 2).

    Phase 1 uses hard-coded distance_miles to prove the scoring pipeline end-to-end.
    """

    score: int = Field(..., ge=0, le=100, description="Raw 0–100 score for this constraint")
    weight_percent: int = Field(60, description="Weight in the blended feasibility score")
    distance_miles: float = Field(..., description="Great-circle distance to nearest substation (mocked in Phase 1)")
    band_label: str = Field(
        ...,
        description="Human-readable bucket: <1 mi, 1–3 mi, or >3 mi",
    )
    data_source: str = Field(..., description="Dataset attribution for judges / compliance")
    rationale: str = Field(
        ...,
        description="Why this factor matters when explaining tradeoffs to a property owner",
    )
    scoring_rules_plain: str = Field(
        ...,
        description="Plain-language description of how the 0–100 subscore is assigned",
    )


class ZoningBreakdown(BaseModel):
    """
    Constraint 2 — nuisance / sensitive receptors within 500 m (OSM Overpass).

    ``residential_percent`` is the **combined** share of the analysis disk covered by residential
    land polygons plus school footprints / buffers (used for the 0–100 subscore).
    """

    score: int = Field(..., ge=0, le=100)
    weight_percent: int = Field(40)
    residential_percent: float = Field(
        ...,
        ge=0,
        le=100,
        description="Combined sensitive coverage % of disk (residential land + schools — score input)",
    )
    residential_land_percent: float = Field(
        ...,
        ge=0,
        le=100,
        description="Residential landuse polygons only, as % of the same disk",
    )
    school_count: int = Field(..., ge=0, description="Distinct OSM school features in radius")
    radius_meters: int = Field(500, description="Analysis disk radius")
    data_source: str
    rationale: str = Field(
        ...,
        description="Why residential adjacency matters for noise, permitting, and neighbor risk",
    )
    scoring_rules_plain: str = Field(
        ...,
        description="Plain-language rule for the residential / noise subscore",
    )


class EvaluateResponse(BaseModel):
    """Full evaluation payload returned to the React dashboard."""

    address: str
    coordinate_source: Literal["geocoded", "user_pin"] = Field(
        ...,
        description="Whether coordinates came from Nominatim or from the client's map pin",
    )
    latitude: float
    longitude: float
    final_score: float = Field(..., ge=0, le=100, description="Weighted blend: 0.6 * power + 0.4 * zoning")
    power: PowerBreakdown
    zoning: ZoningBreakdown
    recommendation_title: str
    recommendation_body: str
    phase_note: str = Field(
        ...,
        description="Explicit banner that Phase 1 uses mocked substation/zoning inputs",
    )
    processing_time_ms: int = Field(
        ...,
        ge=0,
        description="Server-side time to geocode + score (milliseconds); supports the ~1 minute SLA story",
    )
    verdict_plain_english: str = Field(
        ...,
        description="One short paragraph a first-time user can read before diving into numbers",
    )
    formula_display: str = Field(
        ...,
        description="Exact weighting shown in plain text for auditability in front of owners",
    )
    methodology_for_teams: str = Field(
        ...,
        description="How to defend the model in a sales or real-estate conversation",
    )
    coverage_for_teams: str = Field(
        ...,
        description="How the same pipeline applies across regions without retooling the UI",
    )
    owner_talking_points: list[str] = Field(
        ...,
        min_length=1,
        max_length=6,
        description="Short bullets reps can read aloud or drop into email",
    )
