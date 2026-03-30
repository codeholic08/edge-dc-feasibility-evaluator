"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";
import { evaluateAddress } from "@/lib/api";
import type { EvaluateResponse } from "@/lib/types";
import AddressAutocomplete from "@/components/AddressAutocomplete";

const mapLoading = (
  <div className="flex h-[260px] items-center justify-center rounded-xl border border-white/10 bg-white/5 text-sm text-slate-400">
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

/* ── Score Ring ──────────────────────────────────────────── */
function ScoreRing({
  score,
  title,
  icon,
  goodColor,
  badColor,
}: {
  score: number;
  title: string;
  icon: string;
  goodColor: string;
  badColor: string;
}) {
  const clamped = Math.min(100, Math.max(0, score));
  const r = 46;
  const circumference = 2 * Math.PI * r;
  const offset = circumference - (clamped / 100) * circumference;
  const isGood = clamped >= 70;
  const color = isGood ? goodColor : badColor;
  const label = isGood ? "Strong fit" : "Moderate fit";

  return (
    <div className="flex flex-col items-center gap-2">
      <p className="text-[11px] font-bold uppercase tracking-widest text-white/40">{title}</p>
      <span className="text-xl">{icon}</span>
      <div className="relative flex h-36 w-36 items-center justify-center">
        <svg className="h-36 w-36 -rotate-90" viewBox="0 0 120 120" aria-hidden>
          <circle
            className="fill-none"
            stroke="rgba(255,255,255,0.08)"
            strokeWidth="9"
            cx="60" cy="60" r={r}
          />
          <circle
            className="fill-none score-ring-circle"
            stroke={color}
            strokeWidth="9"
            strokeLinecap="round"
            cx="60" cy="60" r={r}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{
              filter: `drop-shadow(0 0 8px ${color})`,
              ["--full-dash" as string]: circumference,
            }}
          />
        </svg>
        <div className="absolute text-center">
          <div className="font-display text-4xl font-bold tabular-nums text-white">
            {clamped.toFixed(0)}
          </div>
          <div className="mt-0.5 text-[10px] font-semibold uppercase tracking-widest text-white/40">
            / 100
          </div>
        </div>
      </div>
      <span
        className="rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-wider"
        style={{
          background: isGood ? `${goodColor}20` : `${badColor}20`,
          border: `1px solid ${isGood ? `${goodColor}50` : `${badColor}50`}`,
          color: isGood ? goodColor : badColor,
        }}
      >
        {label}
      </span>
    </div>
  );
}


/* ── Criterion Card (glass) ─────────────────────────────── */
function CriterionCard({
  icon,
  label,
  score,
  weight,
  solarWeight,
  summaryLine,
  rationale,
  scoringRules,
  dataSource,
  accentColor,
}: {
  icon: string;
  label: string;
  score: number;
  weight: number;
  solarWeight: number;
  summaryLine: string;
  rationale: string;
  scoringRules: string;
  dataSource: string;
  accentColor: string;
}) {
  return (
    <div className="glass rounded-2xl p-5 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-lg"
            style={{ background: `${accentColor}20`, border: `1px solid ${accentColor}30` }}
          >
            {icon}
          </span>
          <div>
            <p className="font-display text-sm font-semibold text-white">{label}</p>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-[10px] text-white/40">⚡ Edge DC: {weight}%</span>
              <span className="text-white/20 text-[10px]">·</span>
              <span className="text-[10px] text-white/40">☀ Solar: {solarWeight}%</span>
            </div>
          </div>
        </div>
        <div
          className="shrink-0 rounded-xl px-3 py-1.5 text-center"
          style={{ background: `${accentColor}15`, border: `1px solid ${accentColor}25` }}
        >
          <div className="font-display text-xl font-bold" style={{ color: accentColor }}>{score}</div>
          <div className="text-[10px] text-white/40">/100</div>
        </div>
      </div>

      <div className="h-2 overflow-hidden rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
        <div
          className="bar-fill h-full rounded-full"
          style={{
            width: `${score}%`,
            background: `linear-gradient(90deg, ${accentColor}99, ${accentColor})`,
            boxShadow: `0 0 10px ${accentColor}60`,
          }}
        />
      </div>

      <p className="text-sm font-medium text-white/80">{summaryLine}</p>
      <p className="text-sm leading-relaxed text-white/55">{rationale}</p>

      <div
        className="rounded-xl px-3 py-2.5 text-xs leading-relaxed"
        style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)" }}
      >
        <span className="font-semibold text-white/70">How we scored it: </span>
        <span className="text-white/50">{scoringRules}</span>
      </div>

      <p className="text-[11px] text-white/30">Source: {dataSource}</p>
    </div>
  );
}

/* ── Talking Point Item ─────────────────────────────────── */
function TalkingPoint({ text, index }: { text: string; index: number }) {
  return (
    <div className="flex gap-3">
      <span
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold"
        style={{ background: "rgba(227,129,76,0.15)", color: "#e3814c", border: "1px solid rgba(227,129,76,0.25)" }}
      >
        {index + 1}
      </span>
      <p className="text-sm leading-relaxed text-white/65">{text}</p>
    </div>
  );
}

/* ── Roadmap Item ───────────────────────────────────────── */
function RoadmapItem({ label, desc, source, live }: { label: string; desc: string; source: string; live: boolean }) {
  return (
    <div className="flex gap-3">
      <span
        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold`}
        style={
          live
            ? { background: "rgba(0,141,127,0.2)", color: "#00b8a6", border: "1px solid rgba(0,141,127,0.3)" }
            : { background: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.3)", border: "1px solid rgba(255,255,255,0.1)" }
        }
      >
        {live ? "✓" : "○"}
      </span>
      <div>
        <p className="text-sm font-semibold text-white/80">
          {label}{" "}
          {live && (
            <span
              className="ml-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
              style={{ background: "rgba(0,141,127,0.2)", color: "#00b8a6" }}
            >
              Live
            </span>
          )}
        </p>
        <p className="mt-0.5 text-xs leading-relaxed text-white/40">{desc}</p>
        <p className="mt-0.5 text-[11px] text-white/25">{source}</p>
      </div>
    </div>
  );
}

/* ── Main Page ──────────────────────────────────────────── */
export default function Home() {
  const [address, setAddress] = useState("");
  const [mapPin, setMapPin] = useState<{ lat: number; lng: number } | null>(null);
  const [preview, setPreview] = useState<{ address: string; lat: number; lng: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EvaluateResponse | null>(null);

  const handlePinChange = useCallback((lat: number, lng: number) => {
    setMapPin({ lat, lng });
    setPreview(null); // manual pin clears autocomplete preview
  }, []);

  const clearMapPin = useCallback(() => {
    setMapPin(null);
    setPreview(null);
  }, []);

  /** Fired when user selects a suggestion from the autocomplete dropdown. */
  const handleAddressSelect = useCallback((displayName: string, lat: number, lng: number) => {
    setAddress(displayName);
    setMapPin({ lat, lng });
    setPreview({ address: displayName, lat, lng });
    setResult(null);
    setError(null);
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
    setPreview(null);
    try {
      const coords = mapPin !== null ? { latitude: mapPin.lat, longitude: mapPin.lng } : null;
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
      <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 lg:px-8">

        {/* ── Hero Header ──────────────────────────────────── */}
        <header className="mb-10">
          <div className="glass rounded-3xl px-8 py-8 sm:px-10">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <span
                    className="rounded-full px-3 py-1 text-[11px] font-bold uppercase tracking-widest"
                    style={{ background: "rgba(227,129,76,0.15)", color: "#e3814c", border: "1px solid rgba(227,129,76,0.25)" }}
                  >
                    Solar Landscape
                  </span>
                  <span className="text-white/20 text-xs">·</span>
                  <span className="text-[11px] text-white/40 uppercase tracking-wider">Sales &amp; Real Estate</span>
                </div>
                <h1 className="font-display text-3xl font-bold leading-tight text-white sm:text-4xl lg:text-5xl">
                  Edge Data Center{" "}
                  <span className="text-gradient-orange">Infrastructure Readiness</span>
                </h1>
                <p className="mt-3 max-w-2xl text-sm leading-relaxed text-white/55 sm:text-base">
                  Fast site screen for real estate and development teams. Six key dimensions scored
                  — power infrastructure, flood resilience, climate burden, connectivity, electricity cost, and area rent pressure.
                  Walk into meetings with numbers.
                </p>
              </div>
              <div
                className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl text-3xl"
                style={{ background: "rgba(227,129,76,0.12)", border: "1px solid rgba(227,129,76,0.2)" }}
              >
                ⚡
              </div>
            </div>
          </div>
        </header>

        {/* ── How it works ─────────────────────────────────── */}
        <section className="mb-8 grid gap-4 sm:grid-cols-3">
          {[
            { step: "01", title: "Enter property address", desc: "Place the building on the map, or type the address to score.", icon: "📍" },
            { step: "02", title: "Get a readiness score", desc: "Edge infrastructure readiness across six dimensions — power, flood, climate, connectivity, electricity cost, and area rent.", icon: "📊" },
            { step: "03", title: "Use the talking points", desc: "Concrete talking points tied to each factor so you can brief leadership with confidence.", icon: "💬" },
          ].map(({ step, title, desc, icon }) => (
            <div key={step} className="glass rounded-2xl p-5">
              <div className="flex items-center gap-3 mb-3">
                <span
                  className="font-display text-xs font-bold uppercase tracking-widest"
                  style={{ color: "#e3814c" }}
                >
                  {step}
                </span>
                <span className="text-xl">{icon}</span>
              </div>
              <p className="font-display text-sm font-semibold text-white">{title}</p>
              <p className="mt-1.5 text-xs leading-relaxed text-white/45">{desc}</p>
            </div>
          ))}
        </section>

        {/* ── Main grid: form + results ─────────────────────── */}
        <div className="grid gap-8 lg:grid-cols-[1fr_1.2fr]">

          {/* ── Left: Input Form ─────────────────────────────── */}
          <div className="space-y-6">
            <form onSubmit={onSubmit} className="glass rounded-3xl p-6 space-y-5">
              <div>
                <h2 className="font-display text-base font-semibold text-white">Evaluate a property</h2>
                <p className="mt-1 text-xs text-white/40">
                  Enter an address, drop a pin, or both.
                </p>
              </div>

              <div>
                <label htmlFor="address" className="block text-xs font-semibold uppercase tracking-wider text-white/50 mb-2">
                  Property address
                  {mapPin !== null && (
                    <span className="ml-2 normal-case font-normal text-white/30">(optional — pin sets the location)</span>
                  )}
                </label>
                <AddressAutocomplete
                  value={address}
                  onChange={setAddress}
                  onSelect={handleAddressSelect}
                  disabled={loading}
                  required={mapPin === null}
                  placeholder="e.g. 601 Bangs Ave, Asbury Park, NJ"
                />
              </div>

              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-white/50 mb-2">
                  Pin location on map
                </p>
                <p className="text-xs text-white/30 mb-3">
                  Click to drop a pin · drag to fine-tune onto the rooftop
                </p>
                <LocationPickMap pin={mapPin} onPinChange={handlePinChange} />
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {mapPin !== null && (
                    <span className="font-mono text-[11px] text-white/40">
                      {mapPin.lat.toFixed(5)}, {mapPin.lng.toFixed(5)}
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={clearMapPin}
                    disabled={mapPin === null}
                    className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-medium text-white/50 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-30"
                  >
                    Clear pin
                  </button>
                </div>
              </div>

              <button type="submit" disabled={loading} className="btn-primary w-full text-center">
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                    </svg>
                    Running screen…
                  </span>
                ) : (
                  "Score this site →"
                )}
              </button>
            </form>

            {error && (
              <div
                className="rounded-2xl px-4 py-3 text-sm"
                style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)", color: "#fca5a5" }}
                role="alert"
              >
                {error}
              </div>
            )}

            {/* ── Scoring framework ──────────────────────────── */}
            <div className="glass rounded-2xl p-5 space-y-4">
              <h3 className="font-display text-sm font-semibold text-white">The six dimensions</h3>
              <p className="text-[11px] text-white/35">All live across the U.S.</p>
              <div className="space-y-4 pt-1">
                <RoadmapItem live label="Power infrastructure" desc="Proximity to transmission-class substations. Distance = trenching cost and grid interconnection feasibility." source="HIFLD Open Data (ArcGIS) · haversine distance" />
                <RoadmapItem live label="Flood risk" desc="FEMA Special Flood Hazard Area (SFHA) designation. Affects insurance, permitting, and resilience planning." source="FEMA NFHL · ArcGIS MapServer layer 28" />
                <RoadmapItem live label="Climate burden" desc="Annual average temperatures and extreme heat days. Drives HVAC load and cooling OPEX." source="Open-Meteo Historical Weather Archive" />
                <RoadmapItem live label="Connectivity readiness" desc="Area-level broadband providers and fiber availability. Lowers dark-fiber cost and improves redundancy." source="FCC Broadband Map · public API" />
                <RoadmapItem live label="Power cost" desc="State-level commercial electricity pricing. A top OPEX line — affects long-term margin." source="EIA Retail Sales API · COM sector" />
                <RoadmapItem live label="Area rent pressure" desc="Census tract median rent. Low rent = favorable alternative-use economics; high rent = competing demands." source="Census ACS · via FCC tract geocoding" />
              </div>
            </div>
          </div>

          {/* ── Right: Results Panel ─────────────────────────── */}
          <div className="space-y-6">
            {/* Location preview — shown after autocomplete selection, before scoring */}
            {!result && !loading && preview && (
              <div className="glass rounded-3xl p-5 space-y-4">
                <div className="flex items-start gap-3">
                  <span
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-lg"
                    style={{ background: "rgba(227,129,76,0.12)", border: "1px solid rgba(227,129,76,0.2)" }}
                  >
                    📍
                  </span>
                  <div className="min-w-0">
                    <p className="text-[11px] font-bold uppercase tracking-widest text-white/35">Selected location</p>
                    <p className="mt-1 font-display text-sm font-semibold leading-snug text-white/85">{preview.address}</p>
                    <p className="mt-1 font-mono text-[11px] text-white/30">
                      {preview.lat.toFixed(5)}, {preview.lng.toFixed(5)}
                    </p>
                  </div>
                </div>
                <div
                  className="rounded-xl px-4 py-3 text-xs text-center"
                  style={{ background: "rgba(227,129,76,0.08)", border: "1px solid rgba(227,129,76,0.18)", color: "rgba(227,129,76,0.8)" }}
                >
                  Pin confirmed — click <strong style={{ color: "#e3814c" }}>Score this site</strong> to run the full analysis
                </div>
              </div>
            )}

            {/* Default empty state */}
            {!result && !loading && !preview && (
              <div
                className="flex min-h-[320px] flex-col items-center justify-center rounded-3xl p-10 text-center"
                style={{ border: "1px dashed rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.02)" }}
              >
                <div
                  className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl text-2xl"
                  style={{ background: "rgba(227,129,76,0.1)", border: "1px solid rgba(227,129,76,0.2)" }}
                >
                  📍
                </div>
                <p className="font-display text-base font-semibold text-white/70">Results appear here</p>
                <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-white/35">
                  Start typing an address to select a location, then score it for edge DC feasibility.
                </p>
              </div>
            )}

            {loading && (
              <div className="glass flex min-h-[200px] flex-col items-center justify-center rounded-3xl p-8 text-center">
                <svg className="mb-4 h-8 w-8 animate-spin" viewBox="0 0 24 24" fill="none" style={{ color: "#e3814c" }}>
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                </svg>
                <p className="font-display text-sm font-semibold text-white/70">
                  {mapPin ? "Scoring your map pin…" : "Geocoding address and scoring…"}
                </p>
                <p className="mt-1 text-xs text-white/35">Usually under 60 seconds</p>
              </div>
            )}

            {result && (
              <div className="space-y-6">

                {/* ── Verdict banner ─────────────────────────── */}
                <div
                  className="rounded-2xl px-5 py-4"
                  style={{ background: "rgba(61,171,216,0.08)", border: "1px solid rgba(61,171,216,0.2)" }}
                >
                  <p className="text-[11px] font-bold uppercase tracking-widest" style={{ color: "#3dabd8" }}>Plain-language read</p>
                  <p className="mt-2 text-sm leading-relaxed text-white/75">{result.verdict_plain_english}</p>
                </div>

                {/* ── Dual Score Rings ───────────────────────── */}
                <div className="glass rounded-3xl p-6 space-y-5">
                  {/* Property meta */}
                  <div>
                    <p className="text-[11px] font-bold uppercase tracking-widest text-white/35">Scored property</p>
                    <p className="mt-1 font-display text-base font-semibold text-white leading-snug">{result.address}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2">
                      <span
                        className="rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
                        style={
                          result.coordinate_source === "user_pin"
                            ? { background: "rgba(236,193,55,0.15)", color: "#ecc137", border: "1px solid rgba(236,193,55,0.25)" }
                            : { background: "rgba(255,255,255,0.07)", color: "rgba(255,255,255,0.5)", border: "1px solid rgba(255,255,255,0.12)" }
                        }
                      >
                        {result.coordinate_source === "user_pin" ? "📍 Scored at your pin" : "🔍 Geocoded coordinates"}
                      </span>
                      <span className="font-mono text-[11px] text-white/25">
                        {result.latitude.toFixed(5)}, {result.longitude.toFixed(5)}
                      </span>
                      <span className="text-[11px] text-white/25">
                        {(result.processing_time_ms / 1000).toFixed(2)}s
                        {slaOk !== null && (
                          <span style={{ color: slaOk ? "#00b8a6" : "#f0a070" }}>
                            {" "}({slaOk ? "✓" : "↑"} 60s)
                          </span>
                        )}
                      </span>
                    </div>
                  </div>

                  {/* Two score rings */}
                  <div className="grid grid-cols-2 gap-4">
                    <div
                      className="flex flex-col items-center rounded-2xl p-4"
                      style={{ background: "rgba(61,171,216,0.06)", border: "1px solid rgba(61,171,216,0.15)" }}
                    >
                      <ScoreRing
                        score={result.edge_dc_score}
                        title="Edge DC Readiness"
                        icon="⚡"
                        goodColor="#3dabd8"
                        badColor="#e3814c"
                      />
                    </div>
                    <div
                      className="flex flex-col items-center rounded-2xl p-4"
                      style={{ background: "rgba(236,193,55,0.06)", border: "1px solid rgba(236,193,55,0.15)" }}
                    >
                      <ScoreRing
                        score={result.solar_score}
                        title="Solar Feasibility"
                        icon="☀️"
                        goodColor="#ecc137"
                        badColor="#e3814c"
                      />
                    </div>
                  </div>

                  {/* Two recommendation pills */}
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div
                      className="rounded-2xl px-4 py-3"
                      style={
                        result.edge_dc_score >= 70
                          ? { background: "rgba(61,171,216,0.08)", border: "1px solid rgba(61,171,216,0.25)" }
                          : { background: "rgba(227,129,76,0.08)", border: "1px solid rgba(227,129,76,0.25)" }
                      }
                    >
                      <p className="text-[10px] font-bold uppercase tracking-widest text-white/35 mb-1">⚡ Edge DC</p>
                      <p
                        className="font-display text-xs font-bold"
                        style={{ color: result.edge_dc_score >= 70 ? "#3dabd8" : "#f0a070" }}
                      >
                        {result.recommendation_title}
                      </p>
                      <p className="mt-1 text-xs leading-relaxed text-white/55">{result.recommendation_body}</p>
                    </div>
                    <div
                      className="rounded-2xl px-4 py-3"
                      style={
                        result.solar_score >= 70
                          ? { background: "rgba(236,193,55,0.08)", border: "1px solid rgba(236,193,55,0.25)" }
                          : { background: "rgba(227,129,76,0.08)", border: "1px solid rgba(227,129,76,0.25)" }
                      }
                    >
                      <p className="text-[10px] font-bold uppercase tracking-widest text-white/35 mb-1">☀️ Solar</p>
                      <p
                        className="font-display text-xs font-bold"
                        style={{ color: result.solar_score >= 70 ? "#ecc137" : "#f0a070" }}
                      >
                        {result.solar_recommendation_title}
                      </p>
                      <p className="mt-1 text-xs leading-relaxed text-white/55">{result.solar_recommendation_body}</p>
                    </div>
                  </div>
                </div>

                {/* ── Five factor breakdown cards ────────────── */}
                <div className="grid gap-4 sm:grid-cols-2">
                  <CriterionCard
                    icon="⚡"
                    label="Power Infrastructure"
                    score={result.power_infrastructure.score}
                    weight={result.power_infrastructure.weight_percent}
                    solarWeight={result.power_infrastructure.solar_weight_percent}
                    summaryLine={`Nearest substation: ${result.power_infrastructure.nearest_substation_distance_km.toFixed(1)} km${
                      result.power_infrastructure.nearest_substation_name ? ` (${result.power_infrastructure.nearest_substation_name})` : ""
                    }`}
                    rationale={result.power_infrastructure.rationale}
                    scoringRules={result.power_infrastructure.scoring_rules_plain}
                    dataSource={result.power_infrastructure.data_source}
                    accentColor="#3dabd8"
                  />
                  <CriterionCard
                    icon="🌊"
                    label="Flood Risk"
                    score={result.flood_risk.score}
                    weight={result.flood_risk.weight_percent}
                    solarWeight={result.flood_risk.solar_weight_percent}
                    summaryLine={`Zone ${result.flood_risk.zone_label}${result.flood_risk.is_high_risk ? " — high risk" : " — low risk"}`}
                    rationale={result.flood_risk.rationale}
                    scoringRules={result.flood_risk.scoring_rules_plain}
                    dataSource={result.flood_risk.data_source}
                    accentColor={result.flood_risk.is_high_risk ? "#e3814c" : "#00b8a6"}
                  />
                  <CriterionCard
                    icon="🌡"
                    label="Climate"
                    score={result.climate_burden.score}
                    weight={result.climate_burden.weight_percent}
                    solarWeight={result.climate_burden.solar_weight_percent}
                    summaryLine={`${result.climate_burden.avg_temp_f.toFixed(1)}°F avg · ${result.climate_burden.extreme_heat_days} heat days/yr · Solar: ${result.climate_burden.solar_score}/100`}
                    rationale={result.climate_burden.rationale}
                    scoringRules={result.climate_burden.scoring_rules_plain}
                    dataSource={result.climate_burden.data_source}
                    accentColor="#ecc137"
                  />
                  <CriterionCard
                    icon="📡"
                    label="Connectivity Readiness"
                    score={result.connectivity_readiness.score}
                    weight={result.connectivity_readiness.weight_percent}
                    solarWeight={result.connectivity_readiness.solar_weight_percent}
                    summaryLine={`${result.connectivity_readiness.provider_count} provider(s) · ${result.connectivity_readiness.fiber_provider_count} fiber · ${result.connectivity_readiness.best_download_mbps.toFixed(0)} Mbps`}
                    rationale={result.connectivity_readiness.rationale}
                    scoringRules={result.connectivity_readiness.scoring_rules_plain}
                    dataSource={result.connectivity_readiness.data_source}
                    accentColor="#00b8a6"
                  />
                  <CriterionCard
                    icon="💵"
                    label="Power Cost"
                    score={result.power_cost.score}
                    weight={result.power_cost.weight_percent}
                    solarWeight={result.power_cost.solar_weight_percent}
                    summaryLine={`${result.power_cost.state_code}: $${result.power_cost.cost_per_kwh.toFixed(3)}/kWh · Solar: ${result.power_cost.solar_score}/100`}
                    rationale={result.power_cost.rationale}
                    scoringRules={result.power_cost.scoring_rules_plain}
                    dataSource={result.power_cost.data_source}
                    accentColor={result.power_cost.score >= 70 ? "#00b8a6" : "#e3814c"}
                  />
                  <CriterionCard
                    icon="🏘️"
                    label="Area Rent Pressure"
                    score={result.area_rent_pressure.score}
                    weight={result.area_rent_pressure.weight_percent}
                    solarWeight={result.area_rent_pressure.solar_weight_percent}
                    summaryLine={`${result.area_rent_pressure.tract_name} — $${result.area_rent_pressure.median_rent_monthly.toLocaleString('en-US', {maximumFractionDigits: 0})}/mo`}
                    rationale={result.area_rent_pressure.rationale}
                    scoringRules={result.area_rent_pressure.scoring_rules_plain}
                    dataSource={result.area_rent_pressure.data_source}
                    accentColor={result.area_rent_pressure.score >= 70 ? "#00b8a6" : "#e3814c"}
                  />
                </div>

                {/* ── Verify map ──────────────────────────────── */}
                <div className="glass rounded-3xl p-5">
                  <h3 className="font-display text-sm font-semibold text-white">Verify scored location</h3>
                  <p className="mt-1 text-xs leading-relaxed text-white/35">
                    {result.coordinate_source === "user_pin"
                      ? "You placed this pin — these coordinates were used for the score. Pan or zoom to confirm."
                      : "Coordinates from geocoding. Confirm the pin sits on the right building; if not, drop a pin and re-run."}
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
                      className="font-medium underline underline-offset-2 transition"
                      style={{ color: "#3dabd8" }}
                    >
                      Open in OpenStreetMap →
                    </a>
                  </p>
                </div>

                {/* ── Talking points ──────────────────────────── */}
                <div className="glass rounded-3xl p-5 space-y-4">
                  <div>
                    <h3 className="font-display text-sm font-semibold text-white">Owner talking points</h3>
                    <p className="mt-1 text-xs text-white/35">Say these out loud — each maps back to a number on this screen.</p>
                  </div>
                  <div className="space-y-3 pt-1">
                    {result.owner_talking_points.map((line, i) => (
                      <TalkingPoint key={i} text={line} index={i} />
                    ))}
                  </div>
                </div>

                {/* ── Data freshness ──────────────────────────── */}
                <div
                  className="rounded-2xl px-4 py-3 text-xs leading-relaxed"
                  style={{ background: "rgba(236,193,55,0.07)", border: "1px solid rgba(236,193,55,0.15)", color: "rgba(236,193,55,0.7)" }}
                >
                  <span className="font-semibold" style={{ color: "#ecc137" }}>Data freshness: </span>
                  {result.phase_note}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
