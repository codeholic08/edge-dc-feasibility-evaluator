"use client";

import { useCallback, useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const markerIcon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

/** Continental US — reasonable default before the user picks a pin. */
const DEFAULT_CENTER: L.LatLngTuple = [39.8283, -98.5795];
const DEFAULT_ZOOM = 4;
const PIN_ZOOM = 17;

export type MapPin = { lat: number; lng: number };

type Props = {
  /** Current pin; `null` means no pin yet (geocode-only on submit). */
  pin: MapPin | null;
  /** Called when the user clicks the map, drags the marker, or you programmatically sync. */
  onPinChange: (lat: number, lng: number) => void;
};

/**
 * Click the map to drop a pin, or drag the pin to nudge it onto the roof.
 * Pairs with the address field: address labels the deal; the pin chooses the exact scored coordinates.
 */
export default function LocationPickMap({ pin, onPinChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const onPinChangeRef = useRef(onPinChange);

  onPinChangeRef.current = onPinChange;

  const syncMarker = useCallback((lat: number, lng: number) => {
    const map = mapRef.current;
    if (!map) return;

    if (!markerRef.current) {
      const m = L.marker([lat, lng], { icon: markerIcon, draggable: true }).addTo(map);
      m.on("dragend", () => {
        const p = m.getLatLng();
        onPinChangeRef.current(p.lat, p.lng);
      });
      markerRef.current = m;
    } else {
      markerRef.current.setLatLng([lat, lng]);
    }
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const map = L.map(el, { scrollWheelZoom: true }).setView(DEFAULT_CENTER, DEFAULT_ZOOM);
    mapRef.current = map;

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    map.on("click", (e: L.LeafletMouseEvent) => {
      const { lat, lng } = e.latlng;
      onPinChangeRef.current(lat, lng);
    });

    requestAnimationFrame(() => map.invalidateSize());

    return () => {
      markerRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (pin === null) {
      markerRef.current?.remove();
      markerRef.current = null;
      return;
    }

    syncMarker(pin.lat, pin.lng);
    map.flyTo([pin.lat, pin.lng], Math.max(map.getZoom(), PIN_ZOOM), { duration: 0.35 });
    requestAnimationFrame(() => map.invalidateSize());
  }, [pin, syncMarker]);

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 shadow-sm">
      <div
        ref={containerRef}
        className="location-pick-map-container h-[min(300px,45vh)] w-full min-h-[220px]"
      />
    </div>
  );
}
