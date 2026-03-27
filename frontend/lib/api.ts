import type { EvaluateResponse } from "./types";

/**
 * Older API processes may not return newer fields; fill gaps so the UI never calls .map on undefined.
 */
function normalizeEvaluateResponse(raw: unknown): EvaluateResponse {
  if (typeof raw !== "object" || raw === null) {
    throw new Error("Invalid response from server");
  }
  const r = raw as Record<string, unknown>;
  const power = (typeof r.power === "object" && r.power !== null ? r.power : {}) as Record<
    string,
    unknown
  >;
  const zoning = (typeof r.zoning === "object" && r.zoning !== null ? r.zoning : {}) as Record<
    string,
    unknown
  >;

  const powerBand =
    typeof power.band_label === "string" ? power.band_label : "";
  const zoningRadius =
    typeof zoning.radius_meters === "number" ? zoning.radius_meters : 500;

  return {
    address: String(r.address ?? ""),
    coordinate_source: r.coordinate_source === "user_pin" ? "user_pin" : "geocoded",
    latitude: Number(r.latitude),
    longitude: Number(r.longitude),
    final_score: Number(r.final_score),
    recommendation_title: String(r.recommendation_title ?? ""),
    recommendation_body: String(r.recommendation_body ?? ""),
    phase_note: String(r.phase_note ?? ""),
    processing_time_ms: typeof r.processing_time_ms === "number" ? r.processing_time_ms : 0,
    verdict_plain_english: String(
      r.verdict_plain_english ??
        "This site was scored using grid proximity and nuisance / zoning pressure (residential + schools). See the recommendation and criteria below.",
    ),
    formula_display: String(
      r.formula_display ??
        "Final score = (60% × grid proximity score) + (40% × nuisance / zoning score). Nuisance uses OSM residential + schools within 500 m.",
    ),
    methodology_for_teams: String(
      r.methodology_for_teams ??
        "We focus on two owner-intuitive risks: reaching serious grid power, and avoiding heavy residential edges that amplify noise and permitting issues. This screen is a conversation starter, not a final engineering sign-off.",
    ),
    coverage_for_teams: String(
      r.coverage_for_teams ??
        "The same workflow applies anywhere the address geocodes: enter a property, get a scored read in seconds to about a minute depending on network conditions.",
    ),
    owner_talking_points: Array.isArray(r.owner_talking_points)
      ? (r.owner_talking_points as unknown[]).map((x) => String(x))
      : [
          `Quick screen: edge data center feasibility is ${Number(r.final_score).toFixed(1)} out of 100 on two headline risks — not a final study.`,
          "Review grid proximity and residential pressure in the criteria cards, then align with the recommendation above.",
        ],
    power: {
      score: Number(power.score),
      weight_percent: Number(power.weight_percent ?? 60),
      distance_miles: Number(power.distance_miles),
      band_label: powerBand,
      data_source: String(power.data_source ?? ""),
      rationale: String(
        power.rationale ??
          "Edge facilities need large, reliable grid power; long distances to transmission-class infrastructure usually mean costly trenching and upgrades.",
      ),
      scoring_rules_plain: String(power.scoring_rules_plain ?? powerBand),
    },
    zoning: {
      score: Number(zoning.score),
      weight_percent: Number(zoning.weight_percent ?? 40),
      residential_percent: Number(zoning.residential_percent ?? 0),
      residential_land_percent:
        typeof zoning.residential_land_percent === "number"
          ? zoning.residential_land_percent
          : Number(zoning.residential_percent ?? 0),
      school_count: typeof zoning.school_count === "number" ? zoning.school_count : 0,
      radius_meters: zoningRadius,
      data_source: String(zoning.data_source ?? ""),
      rationale: String(
        zoning.rationale ??
          "Data centers are loud; residential land and schools nearby raise noise-ordinance and permitting risk. Solar is quiet.",
      ),
      scoring_rules_plain: String(
        zoning.scoring_rules_plain ??
          `Sensitive land share within ${zoningRadius} m of the pin drives this subscore.`,
      ),
    },
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
