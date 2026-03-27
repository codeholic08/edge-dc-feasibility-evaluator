"""
Pydantic models for the public HTTP API.

These shapes mirror what the Next.js dashboard consumes so the contract stays obvious
across all scoring dimensions (power, zoning, climate, flood, air quality, fiber).
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
    Constraint 1 — proximity to high-voltage infrastructure (HIFLD substations).

    Weight: 35% of blended feasibility score.
    """

    score: int = Field(..., ge=0, le=100, description="Raw 0–100 score for this constraint")
    weight_percent: int = Field(35, description="Weight in the blended feasibility score")
    distance_miles: float = Field(..., description="Great-circle distance to nearest substation")
    band_label: str = Field(..., description="Human-readable bucket: <1 mi, 1–3 mi, or >3 mi")
    data_source: str = Field(..., description="Dataset attribution for judges / compliance")
    rationale: str = Field(..., description="Why this factor matters when explaining tradeoffs to a property owner")
    scoring_rules_plain: str = Field(..., description="Plain-language description of how the 0–100 subscore is assigned")


class ZoningBreakdown(BaseModel):
    """
    Constraint 2 — nuisance / sensitive receptors within 500 m (OSM Overpass).

    ``residential_percent`` is the **combined** share of the analysis disk covered by residential
    land polygons plus school footprints / buffers (used for the 0–100 subscore).

    Weight: 25% of blended feasibility score.
    """

    score: int = Field(..., ge=0, le=100)
    weight_percent: int = Field(25)
    residential_percent: float = Field(
        ..., ge=0, le=100,
        description="Combined sensitive coverage % of disk (residential land + schools — score input)",
    )
    residential_land_percent: float = Field(
        ..., ge=0, le=100,
        description="Residential landuse polygons only, as % of the same disk",
    )
    school_count: int = Field(..., ge=0, description="Distinct OSM school features in radius")
    radius_meters: int = Field(500, description="Analysis disk radius")
    data_source: str
    rationale: str = Field(..., description="Why residential adjacency matters for noise, permitting, and neighbor risk")
    scoring_rules_plain: str = Field(..., description="Plain-language rule for the residential / noise subscore")


class ClimateBreakdown(BaseModel):
    """
    Constraint 3 — cooling climate risk from Open-Meteo historical archive.

    Weight: 15% of blended feasibility score.
    """

    score: int = Field(..., ge=0, le=100)
    weight_percent: int = Field(15)
    avg_temp_f: float = Field(..., description="Annual average of daily maximum temperature in °F")
    extreme_heat_days: int = Field(..., ge=0, description="Days per year where daily max exceeded 95 °F")
    data_source: str = Field(..., description="Dataset attribution")
    rationale: str = Field(..., description="Why climate heat load matters for edge DC OPEX")
    scoring_rules_plain: str = Field(..., description="Plain-language scoring bands for temperature and heat days")


class FloodBreakdown(BaseModel):
    """
    Constraint 4 — FEMA flood zone classification (NFHL ArcGIS FeatureServer).

    Weight: 10% of blended feasibility score.
    """

    score: int = Field(..., ge=0, le=100)
    weight_percent: int = Field(10)
    zone_label: str = Field(..., description="Most restrictive FEMA flood zone within 200 m (e.g. AE, X, VE)")
    is_high_risk: bool = Field(..., description="True if any A or V zone intersects the 200 m search radius")
    feature_count: int = Field(..., ge=0, description="Number of FEMA NFHL features found within search radius")
    data_source: str = Field(..., description="Dataset attribution")
    rationale: str = Field(..., description="Why FEMA SFHA designation matters for infrastructure permitting")
    scoring_rules_plain: str = Field(..., description="Plain-language scoring rule for flood zone classification")


class AirQualityBreakdown(BaseModel):
    """
    Constraint 5 — ambient PM2.5 and dust concentrations (Open-Meteo Air Quality API).

    Weight: 8% of blended feasibility score.
    """

    score: int = Field(..., ge=0, le=100)
    weight_percent: int = Field(8)
    avg_pm25: float = Field(..., ge=0, description="7-day hourly mean PM2.5 concentration in µg/m³")
    avg_dust: float = Field(..., ge=0, description="7-day hourly mean dust concentration in µg/m³")
    data_source: str = Field(..., description="Dataset attribution")
    rationale: str = Field(..., description="Why PM2.5 raises filter and permitting costs for edge DCs")
    scoring_rules_plain: str = Field(..., description="Plain-language PM2.5 scoring bands aligned with EPA AQI")


class FiberBreakdown(BaseModel):
    """
    Constraint 6 — fiber conduit and telecom node proximity (OSM Overpass).

    Weight: 7% of blended feasibility score.
    """

    score: int = Field(..., ge=0, le=100)
    weight_percent: int = Field(7)
    fiber_way_count: int = Field(..., ge=0, description="OSM fiber conduit ways within 1000 m")
    telecom_node_count: int = Field(..., ge=0, description="OSM telecom / data-center nodes within 500 m")
    data_source: str = Field(..., description="Dataset attribution")
    rationale: str = Field(..., description="Why mapped street fiber lowers dark-fiber costs for edge DCs")
    scoring_rules_plain: str = Field(..., description="Plain-language scoring bands for fiber way and telecom node counts")


class EvaluateResponse(BaseModel):
    """Full evaluation payload returned to the React dashboard."""

    address: str
    coordinate_source: Literal["geocoded", "user_pin"] = Field(
        ..., description="Whether coordinates came from Nominatim or from the client's map pin",
    )
    latitude: float
    longitude: float
    final_score: float = Field(..., ge=0, le=100, description="Weighted blend across six dimensions")
    power: PowerBreakdown
    zoning: ZoningBreakdown
    climate: ClimateBreakdown
    flood: FloodBreakdown
    air_quality: AirQualityBreakdown
    fiber: FiberBreakdown
    recommendation_title: str
    recommendation_body: str
    phase_note: str = Field(
        ...,
        description=(
            "Banner listing all six live data sources: HIFLD substations (grid), OSM Overpass "
            "(zoning + fiber), Open-Meteo archive (climate), FEMA NFHL (flood), "
            "Open-Meteo AQ (air quality). Service-error fallbacks noted per criterion."
        ),
    )
    processing_time_ms: int = Field(
        ..., ge=0,
        description="Server-side time to geocode + score all six dimensions (milliseconds)",
    )
    verdict_plain_english: str = Field(
        ..., description="One short paragraph a first-time user can read before diving into numbers",
    )
    formula_display: str = Field(
        ..., description="Exact weighting across all six dimensions for auditability",
    )
    methodology_for_teams: str = Field(
        ..., description="How to defend the model in a sales or real-estate conversation",
    )
    coverage_for_teams: str = Field(
        ..., description="How the same pipeline applies across regions without retooling the UI",
    )
    owner_talking_points: list[str] = Field(
        ..., min_length=1, max_length=10,
        description="Short bullets reps can read aloud or drop into email",
    )
