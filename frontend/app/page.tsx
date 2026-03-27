"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";
import { evaluateAddress } from "@/lib/api";
import type { EvaluateResponse } from "@/lib/types";

const mapLoading = (
  <div className="flex h-[min(280px,50vh)] min-h-[220px] items-center justify-center rounded-xl border border-slate-200 bg-slate-50 text-sm text-slate-500">
    Loading map…
  </div>
);

const GeocodedMap = dynamic(() => import("@/components/GeocodedMap"), {
  ssr: false,
  loading: () => mapLoading,
});

const LocationPickMap = dynamic(() => import("@/components/LocationPickMap"), {
  ssr: false,
  loading: () => mapLoading,
});

function ScoreRing({ score }: { score: number }) {
  const clamped = Math.min(100, Math.max(0, score));
  const circumference = 2 * Math.PI * 52;
  const offset = circumference - (clamped / 100) * circumference;
  const strokeClass = clamped >= 70 ? "stroke-emerald-500" : "stroke-amber-500";
  const labelClass = clamped >= 70 ? "text-emerald-600" : "text-amber-700";

  return (
    <div className="relative flex h-36 w-36 shrink-0 items-center justify-center">
      <svg className="h-36 w-36 -rotate-90" viewBox="0 0 120 120" aria-hidden>
        <circle
          className="fill-none stroke-slate-200"
          strokeWidth="10"
          cx="60"
          cy="60"
          r="52"
        />
        <circle
          className={`fill-none ${strokeClass}`}
          strokeWidth="10"
          strokeLinecap="round"
          cx="60"
          cy="60"
          r="52"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <div className={`absolute text-center font-semibold tabular-nums ${labelClass}`}>
        <div className="text-3xl leading-none">{clamped.toFixed(1)}</div>
        <div className="mt-1 max-w-[5.5rem] text-[10px] font-medium uppercase leading-tight tracking-wide text-slate-500">
          Edge DC index
        </div>
      </div>
    </div>
  );
}

function CriterionCard({
  label,
  score,
  weight,
  summaryLine,
  rationale,
  scoringRules,
  dataSource,
}: {
  label: string;
  score: number;
  weight: number;
  summaryLine: string;
  rationale: string;
  scoringRules: string;
  dataSource: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-900">{label}</p>
          <p className="mt-1 text-xs text-slate-500">Counts as {weight}% of the final score</p>
        </div>
        <span className="shrink-0 rounded-md bg-slate-100 px-2 py-1 text-sm font-mono font-medium text-slate-800">
          {score}/100
        </span>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-sky-500 transition-[width] duration-500"
          style={{ width: `${score}%` }}
        />
      </div>
      <p className="mt-3 text-sm font-medium text-slate-800">{summaryLine}</p>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">{rationale}</p>
      <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-700">
        <span className="font-semibold text-slate-800">How we scored it: </span>
        {scoringRules}
      </div>
      <p className="mt-2 text-xs text-slate-500">Source: {dataSource}</p>
    </div>
  );
}

function InfoPanel({
  title,
  children,
  variant = "default",
}: {
  title: string;
  children: React.ReactNode;
  variant?: "default" | "muted";
}) {
  const box =
    variant === "muted"
      ? "border-slate-200 bg-slate-50/90"
      : "border-sky-200/80 bg-sky-50/60";
  return (
    <div className={`rounded-xl border px-4 py-3 ${box}`}>
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">{title}</p>
      <div className="mt-2 text-sm leading-relaxed text-slate-700">{children}</div>
    </div>
  );
}

export default function Home() {
  const [address, setAddress] = useState("");
  const [mapPin, setMapPin] = useState<{ lat: number; lng: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EvaluateResponse | null>(null);

  const handlePinChange = useCallback((lat: number, lng: number) => {
    setMapPin({ lat, lng });
  }, []);

  const clearMapPin = useCallback(() => {
    setMapPin(null);
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (mapPin === null && address.trim().length < 3) {
      setError("Enter an address (3+ characters) or drop a pin on the map.");
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const coords =
        mapPin !== null
          ? { latitude: mapPin.lat, longitude: mapPin.lng }
          : null;
      const data = await evaluateAddress(address, coords);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  const slaOk = result ? result.processing_time_ms < 60_000 : null;

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 lg:px-8">
        <header className="border-b border-slate-200/80 pb-8">
          <p className="text-xs font-semibold uppercase tracking-wider text-sky-800">
            Solar Landscape · Sales &amp; real estate teams
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
            Edge data center vs. rooftop solar — quick site screen
          </h1>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-600 sm:text-base">
            Building owners are weighing edge data centers against rooftop leases. This tool scores{" "}
            <strong className="font-semibold text-slate-800">two live risks</strong>{" "}
            (distance to heavy substations via HIFLD, and nuisance / zoning pressure from{" "}
            <strong className="font-semibold text-slate-800">residential land + schools</strong> in OSM)
            so you can argue with numbers — then expand to cooling, air quality, and architecture in
            conversation.
          </p>
        </header>

        <section
          className="mt-8 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
          aria-label="How to use this tool"
        >
          <h2 className="text-sm font-semibold text-slate-900">First time here? It takes three steps</h2>
          <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-relaxed text-slate-600">
            <li>
              <span className="text-slate-800">Either paste an address</span> (street, city, state){" "}
              <span className="text-slate-800">or drop a pin on the map</span> (or both). With only a pin,
              we score that exact spot; with only an address, we geocode it automatically.
            </li>
            <li>
              <span className="text-slate-800">Read the plain-English verdict</span>, then the{" "}
              <span className="text-slate-800">0–100 index</span> (higher means edge DC looks relatively less
              painful on <em>these two</em> risks — not a full data-center study).
            </li>
            <li>
              <span className="text-slate-800">Use the talking points</span> in your owner meeting or email;
              each line ties back to the math so compliance and leadership can follow the story.
            </li>
          </ol>
          <p className="mt-4 text-xs text-slate-500">
            Design target: <strong className="font-medium text-slate-700">under 60 seconds</strong> per
            lookup nationwide, same workflow whether we geocode or you place a pin.
          </p>
        </section>

        <section
          className="mt-8 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
          aria-label="Owner conversation framework"
        >
          <h2 className="text-sm font-semibold text-slate-900">Five angles reps use (two automated here)</h2>
          <p className="mt-2 text-xs text-slate-500">
            Strong narrative hooks for property owners. Items marked <strong>Live</strong> feed the score;
            others are natural follow-ups for diligence.
          </p>
          <ul className="mt-4 space-y-4 text-sm leading-relaxed text-slate-700">
            <li>
              <span className="font-semibold text-emerald-800">1. Nuisance / zoning (Live)</span> — DCs need
              loud HVAC and backup diesel. Residential zones and schools mean noise complaints and strict
              ordinances; solar is silent.{" "}
              <span className="text-slate-500">Data: OSM Overpass (residential + schools, 500 m).</span>
            </li>
            <li>
              <span className="font-semibold text-emerald-800">2. Grid trenching cost (Live)</span> — Power
              must reach the building; long runs from a major substation mean millions per mile in
              trenching. Solar avoids that CapEx.{" "}
              <span className="text-slate-500">Data: HIFLD substations, straight-line miles.</span>
            </li>
            <li>
              <span className="font-semibold text-slate-800">3. Cooling / heat island (Roadmap)</span> — Urban
              heat raises HVAC load and OPEX.{" "}
              <span className="text-slate-500">Data: OpenWeather, Landsat / USGS.</span>
            </li>
            <li>
              <span className="font-semibold text-slate-800">4. Air quality / PM2.5 (Roadmap)</span> —
              Filters clog near highways and industry.{" "}
              <span className="text-slate-500">Data: EPA AirNow, OpenAQ.</span>
            </li>
            <li>
              <span className="font-semibold text-slate-800">5. “Bunker” fit (Roadmap)</span> — Glazed retail
              or malls are poor DC shells.{" "}
              <span className="text-slate-500">Data: OSM building tags, Street View (future).</span>
            </li>
          </ul>
        </section>

        <section className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
          <div>
            <form onSubmit={onSubmit} className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
              <label htmlFor="address" className="block text-sm font-medium text-slate-800">
                Property address
                {mapPin !== null && (
                  <span className="ml-1 font-normal text-slate-500">(optional — pin sets the location)</span>
                )}
              </label>
              <p className="mt-1 text-xs text-slate-500">
                {mapPin !== null
                  ? "Add an address for the file and talking points, or leave blank and run on the pin only."
                  : "Required unless you drop a pin on the map below. Use the address the owner would recognize."}
              </p>
              <input
                id="address"
                name="address"
                required={mapPin === null}
                minLength={mapPin === null ? 3 : undefined}
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="e.g. 601 Bangs Ave, Asbury Park, NJ"
                autoComplete="street-address"
                className="mt-2 w-full rounded-lg border border-slate-200 bg-slate-50/50 px-3 py-2.5 text-sm text-slate-900 outline-none ring-sky-500/30 placeholder:text-slate-400 focus:border-sky-400 focus:ring-2"
              />

              <div className="mt-5">
                <p className="text-sm font-medium text-slate-800">Property location on the map</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-500">
                Click to drop a pin on the building (drag to adjust). With a pin, you can run the screen
                without typing an address — or add an address too for cleaner records.
              </p>
                <div className="mt-2">
                  <LocationPickMap pin={mapPin} onPinChange={handlePinChange} />
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {mapPin !== null && (
                    <span className="font-mono text-xs text-slate-600">
                      Pin: {mapPin.lat.toFixed(5)}, {mapPin.lng.toFixed(5)}
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={clearMapPin}
                    disabled={mapPin === null}
                    className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Clear pin
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="mt-4 inline-flex w-full items-center justify-center rounded-lg bg-sky-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? "Running screen…" : "Score this site"}
              </button>
            </form>

            {error && (
              <div
                className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
                role="alert"
              >
                {error}
              </div>
            )}
          </div>

          <div className="space-y-6">
            {!result && !loading && (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-white/60 p-8">
                <p className="text-center text-sm font-medium text-slate-700">Results appear here</p>
                <p className="mx-auto mt-2 max-w-md text-center text-sm leading-relaxed text-slate-500">
                  You&apos;ll see a plain-language call, the weighted score, owner-ready talking points, and
                  the exact rules behind each input so the room trusts the recommendation.
                </p>
              </div>
            )}

            {loading && (
              <div className="rounded-2xl border border-slate-200/80 bg-white p-8 text-center text-sm text-slate-600">
                {mapPin
                  ? "Using your map pin and running the scoring model…"
                  : "Geocoding the address and running the scoring model…"}
              </div>
            )}

            {result && (
              <div className="space-y-6">
                <InfoPanel title="Plain-language read" variant="default">
                  <p>{result.verdict_plain_english}</p>
                </InfoPanel>

                <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
                  <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Property
                      </p>
                      <p className="mt-1 text-lg font-medium text-slate-900">{result.address}</p>
                      <p className="mt-2">
                        <span
                          className={
                            result.coordinate_source === "user_pin"
                              ? "inline-flex rounded-full bg-violet-100 px-2.5 py-0.5 text-xs font-semibold text-violet-900"
                              : "inline-flex rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-800"
                          }
                        >
                          {result.coordinate_source === "user_pin"
                            ? "Scored at your map pin"
                            : "Scored at geocoded coordinates"}
                        </span>
                      </p>
                      <p className="mt-2 font-mono text-xs text-slate-500">
                        {result.latitude.toFixed(5)}, {result.longitude.toFixed(5)}
                      </p>
                      <p className="mt-3 text-xs text-slate-500">
                        <span className="font-semibold text-slate-700">Server processing time: </span>
                        {(result.processing_time_ms / 1000).toFixed(2)}s
                        {slaOk !== null && (
                          <span className={slaOk ? " text-emerald-700" : " text-amber-800"}>
                            {" "}
                            ({slaOk ? "within" : "above"} the 60s field guideline)
                          </span>
                        )}
                      </p>
                    </div>
                    <ScoreRing score={result.final_score} />
                  </div>
                  <p className="mt-4 text-xs leading-relaxed text-slate-600">
                    {result.formula_display}
                  </p>
                  <div
                    className={`mt-5 rounded-xl border px-4 py-3 text-sm ${
                      result.final_score >= 70
                        ? "border-emerald-200 bg-emerald-50/80 text-emerald-950"
                        : "border-amber-200 bg-amber-50/80 text-amber-950"
                    }`}
                  >
                    <p className="font-semibold">{result.recommendation_title}</p>
                    <p className="mt-2 leading-relaxed">{result.recommendation_body}</p>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
                  <h3 className="text-sm font-semibold text-slate-900">Verify the scored location</h3>
                  <p className="mt-1 text-xs leading-relaxed text-slate-500">
                    {result.coordinate_source === "user_pin" ? (
                      <>
                        You placed this pin before running the screen — these coordinates were used for
                        the score (the address above is still the property record). Pan or zoom to
                        double-check, or clear the pin and re-run with geocoding only.
                      </>
                    ) : (
                      <>
                        Coordinates came from geocoding your address. Pan or zoom to confirm the pin
                        sits on the right building. If not, add a map pin on the form and run again,
                        or rephrase the address.
                      </>
                    )}
                  </p>
                  <div className="mt-4">
                    <GeocodedMap
                      latitude={result.latitude}
                      longitude={result.longitude}
                      addressLabel={result.address}
                      coordinateSource={result.coordinate_source}
                    />
                  </div>
                  <p className="mt-3 text-center text-xs">
                    <a
                      href={`https://www.openstreetmap.org/?mlat=${result.latitude}&mlon=${result.longitude}&zoom=18`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-sky-700 underline decoration-sky-300 underline-offset-2 hover:text-sky-900"
                    >
                      Open this location in OpenStreetMap
                    </a>
                  </p>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <h3 className="text-sm font-semibold text-slate-900">Talking points for the owner</h3>
                  <p className="mt-1 text-xs text-slate-500">
                    Short lines you can say out loud; each maps to a number on this screen.
                  </p>
                  <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-slate-700">
                    {result.owner_talking_points.map((line, i) => (
                      <li key={i}>{line}</li>
                    ))}
                  </ul>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <CriterionCard
                    label="Grid proximity (high-voltage power)"
                    score={result.power.score}
                    weight={result.power.weight_percent}
                    summaryLine={result.power.band_label}
                    rationale={result.power.rationale}
                    scoringRules={result.power.scoring_rules_plain}
                    dataSource={result.power.data_source}
                  />
                  <CriterionCard
                    label="Nuisance / zoning (residential + schools)"
                    score={result.zoning.score}
                    weight={result.zoning.weight_percent}
                    summaryLine={`${result.zoning.residential_percent}% of the ${result.zoning.radius_meters} m disk is sensitive coverage (combined). Residential land alone: ${result.zoning.residential_land_percent}%. Schools in radius: ${result.zoning.school_count}.`}
                    rationale={result.zoning.rationale}
                    scoringRules={result.zoning.scoring_rules_plain}
                    dataSource={result.zoning.data_source}
                  />
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <InfoPanel title="Why sales can stand behind this" variant="muted">
                    <p>{result.methodology_for_teams}</p>
                  </InfoPanel>
                  <InfoPanel title="Scalability & coverage" variant="muted">
                    <p>{result.coverage_for_teams}</p>
                  </InfoPanel>
                </div>

                <div className="rounded-xl border border-amber-200/80 bg-amber-50/50 px-4 py-3 text-xs leading-relaxed text-amber-950">
                  <span className="font-semibold">Data freshness note: </span>
                  {result.phase_note}
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
