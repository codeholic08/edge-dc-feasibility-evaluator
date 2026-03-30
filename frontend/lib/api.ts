import type { EvaluateResponse } from "./types";

/**
 * Map raw backend response to strongly-typed EvaluateResponse.
 * Provides safe defaults for missing fields to ensure UI never renders undefined.
 */
function normalizeEvaluateResponse(raw: unknown): EvaluateResponse {
  if (typeof raw !== "object" || raw === null) {
    throw new Error("Invalid response from server");
  }
  const r = raw as Record<string, unknown>;

  const safeObject = (obj: unknown): Record<string, unknown> =>
    typeof obj === "object" && obj !== null ? (obj as Record<string, unknown>) : {};

  const infra = safeObject(r.power_infrastructure);
  const flood = safeObject(r.flood_risk);
  const climate = safeObject(r.climate_burden);
  const connectivity = safeObject(r.connectivity_readiness);
  const cost = safeObject(r.power_cost);
  const rent = safeObject(r.area_rent_pressure);

  return {
    address: String(r.address ?? ""),
    coordinate_source: r.coordinate_source === "user_pin" ? "user_pin" : "geocoded",
    latitude: Number(r.latitude ?? 0),
    longitude: Number(r.longitude ?? 0),
    edge_dc_score: Number(r.edge_dc_score ?? 0),
    solar_score: Number(r.solar_score ?? 0),

    power_infrastructure: {
      score: Number(infra.score ?? 0),
      weight_percent: Number(infra.weight_percent ?? 27),
      solar_weight_percent: Number(infra.solar_weight_percent ?? 10),
      nearest_substation_distance_km: Number(infra.nearest_substation_distance_km ?? 0),
      nearest_substation_name: typeof infra.nearest_substation_name === "string" ? infra.nearest_substation_name : undefined,
      data_source: String(infra.data_source ?? "HIFLD"),
      rationale: String(infra.rationale ?? ""),
      scoring_rules_plain: String(infra.scoring_rules_plain ?? ""),
    },

    flood_risk: {
      score: Number(flood.score ?? 0),
      weight_percent: Number(flood.weight_percent ?? 20),
      solar_weight_percent: Number(flood.solar_weight_percent ?? 20),
      zone_label: String(flood.zone_label ?? "Unknown"),
      is_high_risk: flood.is_high_risk === true,
      feature_count: Number(flood.feature_count ?? 0),
      data_source: String(flood.data_source ?? "FEMA NFHL"),
      rationale: String(flood.rationale ?? ""),
      scoring_rules_plain: String(flood.scoring_rules_plain ?? ""),
    },

    climate_burden: {
      score: Number(climate.score ?? 0),
      weight_percent: Number(climate.weight_percent ?? 12),
      solar_score: Number(climate.solar_score ?? 0),
      solar_weight_percent: Number(climate.solar_weight_percent ?? 35),
      avg_temp_f: Number(climate.avg_temp_f ?? 0),
      extreme_heat_days: Number(climate.extreme_heat_days ?? 0),
      data_source: String(climate.data_source ?? "Open-Meteo"),
      rationale: String(climate.rationale ?? ""),
      scoring_rules_plain: String(climate.scoring_rules_plain ?? ""),
    },

    connectivity_readiness: {
      score: Number(connectivity.score ?? 0),
      weight_percent: Number(connectivity.weight_percent ?? 18),
      solar_weight_percent: Number(connectivity.solar_weight_percent ?? 3),
      provider_count: Number(connectivity.provider_count ?? 0),
      fiber_provider_count: Number(connectivity.fiber_provider_count ?? 0),
      best_download_mbps: Number(connectivity.best_download_mbps ?? 0),
      best_upload_mbps: Number(connectivity.best_upload_mbps ?? 0),
      has_symmetric_fiber: connectivity.has_symmetric_fiber === true,
      data_source: String(connectivity.data_source ?? "FCC Broadband Map"),
      rationale: String(connectivity.rationale ?? ""),
      scoring_rules_plain: String(connectivity.scoring_rules_plain ?? ""),
    },

    power_cost: {
      score: Number(cost.score ?? 0),
      weight_percent: Number(cost.weight_percent ?? 13),
      solar_score: Number(cost.solar_score ?? 0),
      solar_weight_percent: Number(cost.solar_weight_percent ?? 25),
      state_code: String(cost.state_code ?? "US"),
      latest_period: String(cost.latest_period ?? ""),
      cost_per_kwh: Number(cost.cost_per_kwh ?? 0),
      sector_used: String(cost.sector_used ?? "COM"),
      data_source: String(cost.data_source ?? "EIA"),
      rationale: String(cost.rationale ?? ""),
      scoring_rules_plain: String(cost.scoring_rules_plain ?? ""),
    },

    area_rent_pressure: {
      score: Number(rent.score ?? 0),
      weight_percent: Number(rent.weight_percent ?? 10),
      solar_weight_percent: Number(rent.solar_weight_percent ?? 7),
      tract_name: String(rent.tract_name ?? "Unknown"),
      state_code: String(rent.state_code ?? "US"),
      county_code: String(rent.county_code ?? "000"),
      tract_code: String(rent.tract_code ?? "000000"),
      median_rent_monthly: Number(rent.median_rent_monthly ?? 0),
      rent_metric_type: String(rent.rent_metric_type ?? "unknown"),
      fallback_used: rent.fallback_used === true,
      data_source: String(rent.data_source ?? "Census ACS"),
      rationale: String(rent.rationale ?? ""),
      scoring_rules_plain: String(rent.scoring_rules_plain ?? ""),
    },

    recommendation_title: String(r.recommendation_title ?? ""),
    recommendation_body: String(r.recommendation_body ?? ""),
    solar_recommendation_title: String(r.solar_recommendation_title ?? ""),
    solar_recommendation_body: String(r.solar_recommendation_body ?? ""),
    phase_note: String(r.phase_note ?? ""),
    processing_time_ms: typeof r.processing_time_ms === "number" ? r.processing_time_ms : 0,
    verdict_plain_english: String(
      r.verdict_plain_english ??
        "This site was evaluated across six key dimensions.",
    ),
    formula_display: String(
      r.formula_display ??
        "Edge DC: 27% power infra + 20% flood + 18% connectivity + 12% climate + 13% power cost + 10% rent. Solar: 35% climate + 25% power cost + 20% flood + 10% power infra + 7% rent + 3% connectivity.",
    ),
    methodology_for_teams: String(
      r.methodology_for_teams ??
        "Both scores use the same six live data dimensions with different weightings.",
    ),
    coverage_for_teams: String(
      r.coverage_for_teams ??
        "This evaluation works for any U.S. commercial address.",
    ),
    owner_talking_points: Array.isArray(r.owner_talking_points)
      ? (r.owner_talking_points as unknown[]).map((x) => String(x))
      : [
          `Edge DC score: ${Number(r.edge_dc_score ?? 0).toFixed(1)} / 100. Solar score: ${Number(r.solar_score ?? 0).toFixed(1)} / 100.`,
          "See the detailed breakdown below for each factor.",
        ],
  };
}

/**
 * Base URL for FastAPI.
 *
 * Default: same-origin path `/api/backend`, which Next.js rewrites to FastAPI (see
 * `next.config.ts`). That avoids CORS when you open the app via a LAN URL like
 * `http://192.168.x.x:3000` instead of localhost.
 *
 * Set `NEXT_PUBLIC_API_URL` (e.g. `https://api.example.com`) only when the browser must call
 * the API directly (production CORS must allow your site origin).
 */
export function getApiBase(): string {
  const fromEnv = process.env.NEXT_PUBLIC_API_URL;
  if (fromEnv) return fromEnv.replace(/\/$/, "");
  return "/api/backend";
}

export type EvaluateCoordinates = { latitude: number; longitude: number };

/**
 * @param coordinates Optional WGS84 pin from the map; when set, the API skips geocoding and scores this exact point.
 */
export async function evaluateAddress(
  address: string,
  coordinates?: EvaluateCoordinates | null,
): Promise<EvaluateResponse> {
  const payload: Record<string, unknown> = { address: address.trim() };
  if (coordinates != null) {
    payload.latitude = coordinates.latitude;
    payload.longitude = coordinates.longitude;
  }

  const res = await fetch(`${getApiBase()}/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = { detail: text };
  }

  if (!res.ok) {
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : res.statusText;
    throw new Error(detail || `Request failed (${res.status})`);
  }

  return normalizeEvaluateResponse(body);
}
