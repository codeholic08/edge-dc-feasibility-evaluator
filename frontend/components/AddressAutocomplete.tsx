"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { searchAddressSuggestions, type NominatimSuggestion } from "@/lib/nominatim";

type Props = {
  value: string;
  onChange: (value: string) => void;
  /** Fired when the user selects a suggestion — provides geocoded coordinates. */
  onSelect: (displayName: string, lat: number, lng: number) => void;
  disabled?: boolean;
  placeholder?: string;
  required?: boolean;
};

const DEBOUNCE_MS = 350;

export default function AddressAutocomplete({
  value,
  onChange,
  onSelect,
  disabled = false,
  placeholder = "e.g. 601 Bangs Ave, Asbury Park, NJ",
  required = false,
}: Props) {
  const [suggestions, setSuggestions] = useState<NominatimSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [searching, setSearching] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  /* ── Trigger Nominatim search with debounce ─── */
  const triggerSearch = useCallback((query: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (abortRef.current) abortRef.current.abort();

    if (query.trim().length < 3) {
      setSuggestions([]);
      setOpen(false);
      setSearching(false);
      return;
    }

    setSearching(true);
    debounceRef.current = setTimeout(async () => {
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      const results = await searchAddressSuggestions(query, ctrl.signal);
      if (!ctrl.signal.aborted) {
        setSuggestions(results);
        setOpen(results.length > 0);
        setActiveIndex(-1);
        setSearching(false);
      }
    }, DEBOUNCE_MS);
  }, []);

  /* ── Handle input change ─── */
  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value;
    onChange(v);
    triggerSearch(v);
  }

  /* ── Handle suggestion click ─── */
  function handleSelect(s: NominatimSuggestion) {
    onChange(s.display_name);
    onSelect(s.display_name, parseFloat(s.lat), parseFloat(s.lon));
    setSuggestions([]);
    setOpen(false);
    setActiveIndex(-1);
    inputRef.current?.blur();
  }

  /* ── Keyboard navigation ─── */
  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      handleSelect(suggestions[activeIndex]);
    } else if (e.key === "Escape") {
      setOpen(false);
      setActiveIndex(-1);
    }
  }

  /* ── Close on outside click ─── */
  useEffect(() => {
    function onPointerDown(e: PointerEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setActiveIndex(-1);
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, []);

  /* ── Cleanup on unmount ─── */
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  return (
    <div ref={containerRef} className="relative">
      {/* Input */}
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          disabled={disabled}
          required={required}
          placeholder={placeholder}
          autoComplete="off"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-haspopup="listbox"
          className="glass-input w-full px-4 py-3 pr-10 text-sm"
        />
        {/* Spinner / search icon */}
        <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2">
          {searching ? (
            <svg
              className="h-4 w-4 animate-spin"
              viewBox="0 0 24 24"
              fill="none"
              style={{ color: "rgba(227,129,76,0.7)" }}
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
          ) : (
            <svg
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
              style={{ color: "rgba(255,255,255,0.2)" }}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
            </svg>
          )}
        </div>
      </div>

      {/* Dropdown */}
      {open && suggestions.length > 0 && (
        <ul
          role="listbox"
          className="absolute left-0 right-0 z-50 mt-1.5 overflow-hidden rounded-xl"
          style={{
            background: "rgba(10,18,35,0.97)",
            backdropFilter: "blur(24px)",
            WebkitBackdropFilter: "blur(24px)",
            border: "1px solid rgba(255,255,255,0.12)",
            boxShadow: "0 16px 48px rgba(0,0,0,0.7)",
          }}
        >
          {suggestions.map((s, i) => (
            <li
              key={s.place_id}
              role="option"
              aria-selected={i === activeIndex}
              onPointerDown={(e) => {
                e.preventDefault(); // prevent input blur before click fires
                handleSelect(s);
              }}
              className="flex cursor-pointer items-start gap-3 px-4 py-3 transition-colors"
              style={{
                background: i === activeIndex ? "rgba(227,129,76,0.1)" : "transparent",
                borderBottom: i < suggestions.length - 1 ? "1px solid rgba(255,255,255,0.05)" : "none",
              }}
            >
              <span className="mt-0.5 shrink-0 text-base" style={{ color: "rgba(227,129,76,0.7)" }}>
                📍
              </span>
              <span className="text-sm leading-snug text-white/75">{s.display_name}</span>
            </li>
          ))}
          <li className="px-4 py-2 text-[10px] text-white/20">
            Powered by OpenStreetMap Nominatim
          </li>
        </ul>
      )}
    </div>
  );
}
