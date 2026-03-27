/**
 * Nominatim forward-geocode search for address autocomplete.
 * No API key required. Respects Nominatim's usage policy via a descriptive User-Agent.
 */

export type NominatimSuggestion = {
  place_id: number;
  display_name: string;
  lat: string;
  lon: string;
  type: string;
  class: string;
};

/**
 * Search Nominatim for up to 5 address suggestions.
 * Returns an empty array on any error or if query is too short.
 * Pass an AbortSignal to cancel in-flight requests when the query changes.
 */
export async function searchAddressSuggestions(
  query: string,
  signal?: AbortSignal,
): Promise<NominatimSuggestion[]> {
  if (query.trim().length < 3) return [];

  const params = new URLSearchParams({
    q: query.trim(),
    format: "json",
    limit: "5",
    addressdetails: "0",
  });

  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/search?${params.toString()}`,
      {
        headers: {
          "User-Agent": "EdgeDataCenterFeasibilityEvaluator/1.0 (hackathon)",
          "Accept-Language": "en",
        },
        signal,
      },
    );
    if (!res.ok) return [];
    return (await res.json()) as NominatimSuggestion[];
  } catch {
    // AbortError is expected when the user types quickly — swallow silently
    return [];
  }
}
