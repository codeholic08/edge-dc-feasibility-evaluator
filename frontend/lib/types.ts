/**
 * Mirrors backend/schemas.py for type-safe fetch handling.
 */

export type PowerBreakdown = {
  score: number;
  weight_percent: number;
  distance_miles: number;
  band_label: string;
  data_source: string;
  rationale: string;
  scoring_rules_plain: string;
};

export type ZoningBreakdown = {
  score: number;
  weight_percent: number;
  /** Combined sensitive coverage of the analysis disk (residential + schools) — score input. */
  residential_percent: number;
  /** Residential landuse polygons only (% of same disk). */
  residential_land_percent: number;
  school_count: number;
  radius_meters: number;
  data_source: string;
  rationale: string;
  scoring_rules_plain: string;
};

export type EvaluateResponse = {
  address: string;
  /** Coordinates from Nominatim vs. map pin the rep placed. */
  coordinate_source: "geocoded" | "user_pin";
  latitude: number;
  longitude: number;
  final_score: number;
  power: PowerBreakdown;
  zoning: ZoningBreakdown;
  recommendation_title: string;
  recommendation_body: string;
  phase_note: string;
  processing_time_ms: number;
  verdict_plain_english: string;
  formula_display: string;
  methodology_for_teams: string;
  coverage_for_teams: string;
  owner_talking_points: string[];
};
