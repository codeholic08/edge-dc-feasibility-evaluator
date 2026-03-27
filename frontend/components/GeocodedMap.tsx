"use client";

import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

/** Bundlers often break Leaflet's default marker images; use CDN assets. */
const markerIcon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

type Props = {
  latitude: number;
  longitude: number;
  /** Shown in the marker popup (e.g. the address the user typed). */
  addressLabel: string;
  /** Matches API `coordinate_source` for popup wording. */
  coordinateSource?: "geocoded" | "user_pin";
};

/**
 * Interactive OpenStreetMap view centered on the scored coordinates.
 * Client-only: Leaflet touches `window`, so load this with `next/dynamic({ ssr: false })`.
 */
export default function GeocodedMap({
  latitude,
  longitude,
  addressLabel,
  coordinateSource = "geocoded",
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const map = L.map(el, {
      scrollWheelZoom: true,
    }).setView([latitude, longitude], 17);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    const pinTitle =
      coordinateSource === "user_pin" ? "Your map pin (scored here)" : "Geocoded pin";

    L.marker([latitude, longitude], { icon: markerIcon })
      .addTo(map)
      .bindPopup(`<strong>${escapeHtml(pinTitle)}</strong><br/>${escapeHtml(addressLabel)}`);

    requestAnimationFrame(() => map.invalidateSize());

    return () => {
      map.remove();
    };
  }, [latitude, longitude, addressLabel, coordinateSource]);

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 shadow-sm">
      <div ref={containerRef} className="geocoded-map-container h-[min(280px,50vh)] w-full min-h-[220px]" />
    </div>
  );
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
