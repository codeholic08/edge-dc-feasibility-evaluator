/**
 * Mirrors backend/schemas.py — dual Solar + Edge DC feasibility scoring.
 */

export type PowerInfrastructureBreakdown = {
  score: number;
  weight_percent: number;       // Edge DC weight (27%)
  solar_weight_percent: number; // Solar weight (10%)
  nearest_substation_distance_km: number;
  nearest_substation_name?: string;
  data_source: string;
  rationale: string;
  scoring_rules_plain: string;
};

export type FloodRiskBreakdown = {
  score: number;
  weight_percent: number;       // Edge DC weight (20%)
  solar_weight_percent: number; // Solar weight (20%)
  zone_label: string;
  is_high_risk: boolean;
  feature_count: number;
  data_source: string;
  rationale: string;
  scoring_rules_plain: string;
};

export type ClimateBurdenBreakdown = {
  score: number;               // Edge DC climate score (cool = high)
  weight_percent: number;      // Edge DC weight (12%)
  solar_score: number;         // Solar climate score (hot = high)
  solar_weight_percent: number;// Solar weight (35%)
  avg_temp_f: number;
  extreme_heat_days: number;
  data_source: string;
  rationale: string;
  scoring_rules_plain: string;
};

export type ConnectivityReadinessBreakdown = {
  score: number;
  weight_percent: number;       // Edge DC weight (18%)
  solar_weight_percent: number; // Solar weight (3%)
  provider_count: number;
  fiber_provider_count: number;
  best_download_mbps: number;
  best_upload_mbps: number;
  has_symmetric_fiber: boolean;
  data_source: string;
  rationale: string;
  scoring_rules_plain: string;
};

export type PowerCostBreakdown = {
  score: number;               // Edge DC power cost score (cheap = high)
  weight_percent: number;      // Edge DC weight (13%)
  solar_score: number;         // Solar power cost score (expensive = high)
  solar_weight_percent: number;// Solar weight (25%)
  state_code: string;
  latest_period: string;
  cost_per_kwh: number;
  sector_used: string;
  data_source: string;
  rationale: string;
  scoring_rules_plain: string;
};

export type AreaRentPressureBreakdown = {
  score: number;
  weight_percent: number;       // Edge DC weight (10%)
  solar_weight_percent: number; // Solar weight (7%)
  tract_name: string;
  state_code: string;
  county_code: string;
  tract_code: string;
  median_rent_monthly: number;
  rent_metric_type: string;
  fallback_used: boolean;
  data_source: string;
  rationale: string;
  scoring_rules_plain: string;
};

export type EvaluateResponse = {
  address: string;
  coordinate_source: "geocoded" | "user_pin";
  latitude: number;
  longitude: number;
  edge_dc_score: number;
  solar_score: number;
  power_infrastructure: PowerInfrastructureBreakdown;
  flood_risk: FloodRiskBreakdown;
  climate_burden: ClimateBurdenBreakdown;
  connectivity_readiness: ConnectivityReadinessBreakdown;
  power_cost: PowerCostBreakdown;
  area_rent_pressure: AreaRentPressureBreakdown;
  recommendation_title: string;
  recommendation_body: string;
  solar_recommendation_title: string;
  solar_recommendation_body: string;
  phase_note: string;
  processing_time_ms: number;
  verdict_plain_english: string;
  formula_display: string;
  methodology_for_teams: string;
  coverage_for_teams: string;
  owner_talking_points: string[];
};
