"""
Pydantic models for the public HTTP API.

These shapes mirror what the Next.js dashboard consumes so the contract stays obvious
across all six scoring dimensions of the Edge Infrastructure Readiness Score:
  power infrastructure, flood risk, climate burden, connectivity readiness, power cost, area rent pressure.
"""

from __future__ import annotations

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


class PowerInfrastructureBreakdown(BaseModel):
    """
    Factor 1 — proximity to transmission-class substations (HIFLD Open Data / ArcGIS).

    Weight: 27% Edge DC / 10% Solar.
    """

    score: int = Field(..., ge=0, le=100, description="Raw 0–100 score for this factor")
    weight_percent: int = Field(28, description="Edge DC weight in the blended readiness score")
    solar_weight_percent: int = Field(10, description="Solar weight in the solar feasibility score")
    nearest_substation_distance_km: float = Field(
        ..., description="Great-circle distance to the nearest HIFLD substation in kilometres",
    )
    nearest_substation_name: Optional[str] = Field(
        None, description="NAME attribute of the nearest substation feature, if present",
    )
    data_source: str = Field(..., description="Dataset attribution for auditability")
    rationale: str = Field(..., description="Why substation proximity matters for edge DC economics")
    scoring_rules_plain: str = Field(..., description="Plain-language description of the 0–100 scoring bands")


class FloodRiskBreakdown(BaseModel):
    """
    Factor 2 — FEMA flood zone classification near the pin (NFHL ArcGIS FeatureServer).

    Weight: 20% Edge DC / 20% Solar.
    """

    score: int = Field(..., ge=0, le=100)
    weight_percent: int = Field(18)
    solar_weight_percent: int = Field(30)
    zone_label: str = Field(..., description="Most restrictive FEMA flood zone within 200 m (e.g. AE, X, VE)")
    is_high_risk: bool = Field(..., description="True if any A or V zone intersects the 200 m search radius")
    feature_count: int = Field(..., ge=0, description="Number of FEMA NFHL features found within search radius")
    data_source: str = Field(..., description="Dataset attribution")
    rationale: str = Field(..., description="Why FEMA SFHA designation matters for infrastructure resilience")
    scoring_rules_plain: str = Field(..., description="Plain-language scoring rule for flood zone classification")


class ClimateBurdenBreakdown(BaseModel):
    """
    Factor 3 — cooling risk (Edge DC) / generation potential (Solar) from Open-Meteo.

    Edge DC weight: 12% — cool = good (lower HVAC costs).
    Solar weight:   35% — hot  = good (higher irradiance / generation).
    """

    score: int = Field(..., ge=0, le=100, description="Edge DC climate score (cool = high)")
    weight_percent: int = Field(12, description="Edge DC weight")
    solar_score: int = Field(..., ge=0, le=100, description="Solar climate score (hot = high)")
    solar_weight_percent: int = Field(28, description="Solar weight")
    avg_temp_f: float = Field(..., description="Annual average of daily maximum temperature in °F")
    extreme_heat_days: int = Field(..., ge=0, description="Days per year where daily max exceeded 95 °F")
    data_source: str = Field(..., description="Dataset attribution")
    rationale: str = Field(..., description="Why climate heat load matters for edge DC OPEX")
    scoring_rules_plain: str = Field(..., description="Plain-language scoring bands for temperature and heat days")


class ConnectivityReadinessBreakdown(BaseModel):
    """
    Factor 4 — area-level broadband and fiber availability (FCC Broadband Map public API).

    Weight: 18% Edge DC / 3% Solar.
    """

    score: int = Field(..., ge=0, le=100)
    weight_percent: int = Field(22)
    solar_weight_percent: int = Field(4)
    provider_count: int = Field(..., ge=0, description="Distinct broadband providers serving the area near the pin")
    fiber_provider_count: int = Field(..., ge=0, description="Providers offering fiber-based service near the pin")
    best_download_mbps: float = Field(..., ge=0, description="Peak advertised download speed across all providers (Mbps)")
    best_upload_mbps: float = Field(..., ge=0, description="Peak advertised upload speed across all providers (Mbps)")
    has_symmetric_fiber: bool = Field(
        ..., description="True if a fiber provider offers upload ≥ 80% of download speed",
    )
    data_source: str = Field(..., description="Dataset attribution")
    rationale: str = Field(..., description="Why broadband / fiber availability matters for edge DC connectivity")
    scoring_rules_plain: str = Field(..., description="Plain-language scoring bands for provider and fiber availability")


class PowerCostBreakdown(BaseModel):
    """
    Factor 5 — area-level commercial electricity price by state (EIA v2 retail-sales API).

    Edge DC weight: 13% — cheap = good (lower OPEX).
    Solar weight:   25% — expensive = good (better savings ROI).
    """

    score: int = Field(..., ge=0, le=100, description="Edge DC power cost score (cheap = high)")
    weight_percent: int = Field(13, description="Edge DC weight")
    solar_score: int = Field(..., ge=0, le=100, description="Solar power cost score (expensive = high)")
    solar_weight_percent: int = Field(20, description="Solar weight")
    state_code: str = Field(..., description="Two-letter EIA state code derived from reverse geocoding")
    latest_period: str = Field(..., description="Most recent monthly period returned by EIA (e.g. 2024-11)")
    cost_per_kwh: float = Field(..., ge=0, description="Commercial electricity price in $/kWh")
    sector_used: str = Field(..., description="EIA sector queried (COM = commercial)")
    data_source: str = Field(..., description="Dataset attribution")
    rationale: str = Field(..., description="Why electricity price matters for long-term edge DC economics")
    scoring_rules_plain: str = Field(..., description="Plain-language scoring bands for $/kWh commercial rate")


class AreaRentPressureBreakdown(BaseModel):
    """
    Factor 6 — area-level median rent pressure via FCC Census lookup + Census ACS 5-year.

    Weight: 10% Edge DC / 7% Solar.
    """

    score: int = Field(..., ge=0, le=100)
    weight_percent: int = Field(7)
    solar_weight_percent: int = Field(8)
    tract_name: str = Field(..., description="Census tract name and geography identifier")
    state_code: str = Field(..., description="Two-digit Census state FIPS code")
    county_code: str = Field(..., description="Three-digit County FIPS code")
    tract_code: str = Field(..., description="Six-digit Census tract code")
    median_rent_monthly: float = Field(..., ge=0, description="Median monthly rent for the tract (dollars)")
    rent_metric_type: str = Field(..., description="Type of rent metric (gross_rent or contract_rent)")
    fallback_used: bool = Field(..., description="True if Census API was unavailable and fallback estimate was used")
    data_source: str = Field(..., description="Dataset attribution and provenance")
    rationale: str = Field(..., description="Why area rent pressure matters for edge DC site economics")
    scoring_rules_plain: str = Field(..., description="Plain-language scoring bands for median rent")


class EvaluateResponse(BaseModel):
    """Full evaluation payload returned to the React dashboard."""

    address: str
    coordinate_source: Literal["geocoded", "user_pin"] = Field(
        ..., description="Whether coordinates came from Nominatim or from the client's map pin",
    )
    latitude: float
    longitude: float
    edge_dc_score: float = Field(
        ..., ge=0, le=100,
        description="Weighted Edge DC Infrastructure Readiness Score (0–100)",
    )
    solar_score: float = Field(
        ..., ge=0, le=100,
        description="Weighted Solar Feasibility Score (0–100)",
    )
    power_infrastructure: PowerInfrastructureBreakdown
    flood_risk: FloodRiskBreakdown
    climate_burden: ClimateBurdenBreakdown
    connectivity_readiness: ConnectivityReadinessBreakdown
    power_cost: PowerCostBreakdown
    area_rent_pressure: AreaRentPressureBreakdown
    recommendation_title: str
    recommendation_body: str
    solar_recommendation_title: str
    solar_recommendation_body: str
    phase_note: str = Field(
        ...,
        description=(
            "Banner listing all six live data sources: HIFLD substations (power infrastructure), "
            "FEMA NFHL (flood risk), Open-Meteo archive (climate burden), "
            "FCC Broadband Map (connectivity readiness), EIA retail-sales API (power cost), "
            "Census ACS (area rent pressure). Service-error fallbacks noted per criterion."
        ),
    )
    processing_time_ms: int = Field(
        ..., ge=0,
        description="Server-side time to geocode + score all five dimensions (milliseconds)",
    )
    verdict_plain_english: str = Field(
        ..., description="One short paragraph a first-time user can read before diving into numbers",
    )
    formula_display: str = Field(
        ..., description="Exact weighting across all five dimensions for auditability",
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
