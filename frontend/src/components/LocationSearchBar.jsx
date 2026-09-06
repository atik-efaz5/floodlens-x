import { useEffect, useId, useState } from "react";

import { searchLocations } from "../api";
import { parseCoordinateQuery } from "../utils/locationSearch";

function looksLikeCoordinates(query) {
  return /^-?\d+(\.\d+)?\s*[, ]\s*-?\d+(\.\d+)?$/.test(query.trim());
}

export default function LocationSearchBar({ onSelectLocation, variant = "overlay" }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [noResults, setNoResults] = useState(false);
  const [invalid, setInvalid] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const listId = useId();

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setResults([]);
      setIsOpen(false);
      setNoResults(false);
      setError(null);
      setInvalid(false);
      return undefined;
    }

    if (looksLikeCoordinates(trimmed) && !parseCoordinateQuery(trimmed)) {
      setResults([]);
      setIsOpen(true);
      setNoResults(false);
      setError(null);
      setInvalid(true);
      setLoading(false);
      return undefined;
    }

    const coordinateMatch = parseCoordinateQuery(trimmed);
    if (coordinateMatch) {
      setResults([coordinateMatch]);
      setIsOpen(true);
      setActiveIndex(0);
      setNoResults(false);
      setError(null);
      setInvalid(false);
      setLoading(false);
      return undefined;
    }

    const timeoutId = window.setTimeout(async () => {
      setLoading(true);
      setError(null);
      setNoResults(false);
      setInvalid(false);
      try {
        const payload = await searchLocations(trimmed);
        setResults(payload.results || []);
        setIsOpen(true);
        setActiveIndex(0);
        setNoResults((payload.results || []).length === 0);
      } catch (searchError) {
        setResults([]);
        setIsOpen(true);
        setError(searchError.message);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => window.clearTimeout(timeoutId);
  }, [query]);

  const handleSelect = (location) => {
    setQuery(location.display_name);
    setIsOpen(false);
    setError(null);
    onSelectLocation(location);
  };

  const handleClear = () => {
    setQuery("");
    setResults([]);
    setIsOpen(false);
    setNoResults(false);
    setError(null);
    setInvalid(false);
    onSelectLocation?.({
      display_name: "",
      latitude: null,
      longitude: null,
      cleared: true,
    });
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    if (results.length > 0) {
      handleSelect(results[Math.min(activeIndex, results.length - 1)]);
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === "Escape") {
      setIsOpen(false);
      return;
    }
    if (!isOpen || !results.length) {
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) => Math.min(current + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => Math.max(current - 1, 0));
    }
  };

  const wrapperClass =
    variant === "header"
      ? "relative z-[1000] w-[min(420px,100%)]"
      : "pointer-events-auto absolute left-1/2 top-4 z-[1000] w-[min(420px,calc(100%-2rem))] -translate-x-1/2";

  return (
    <div className={wrapperClass}>
      <form
        onSubmit={handleSubmit}
        className="rounded-2xl border border-white/15 bg-white/95 shadow-xl backdrop-blur"
      >
        <div className="flex items-center">
          <input
            type="search"
            role="combobox"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search country, city, district, river, neighborhood, region ID, or lat, lon"
            aria-label="Location search"
            aria-autocomplete="list"
            aria-expanded={isOpen}
            aria-controls={listId}
            aria-activedescendant={
              isOpen && results[activeIndex] ? `${listId}-opt-${activeIndex}` : undefined
            }
            className={`w-full px-4 py-3 text-sm text-slate-900 outline-none ${
              variant === "header" ? "rounded-xl" : "rounded-2xl"
            }`}
          />
          {query && (
            <button
              type="button"
              onClick={handleClear}
              aria-label="Clear location search"
              className="mr-2 rounded-full px-2 py-1 text-xs font-semibold uppercase tracking-wide text-slate-500 hover:bg-slate-100"
            >
              Clear
            </button>
          )}
        </div>
        <div className="sr-only" aria-live="polite">
          {loading ? "Searching" : ""}
          {noResults ? "No results found" : ""}
          {invalid ? "Invalid coordinate query" : ""}
          {error ? `Search error ${error}` : ""}
          {results.length > 1 ? `${results.length} matches. Use arrows to disambiguate.` : ""}
        </div>
        {isOpen && (
          <div className="border-t border-slate-200" id={listId} role="listbox">
            {loading && (
              <p className="px-4 py-3 text-sm text-slate-500">Searching...</p>
            )}
            {invalid && (
              <p className="px-4 py-3 text-sm text-red-600">Invalid coordinates. Use latitude, longitude.</p>
            )}
            {error && (
              <p className="px-4 py-3 text-sm text-red-600">{error}</p>
            )}
            {!loading && !error && !invalid && noResults && (
              <p className="px-4 py-3 text-sm text-slate-500">No results found.</p>
            )}
            {!loading && !error && results.length > 0 && (
              <ul className="max-h-56 overflow-y-auto">
                {results.map((location, index) => (
                  <li key={`${location.display_name}-${index}`}>
                    <button
                      type="button"
                      id={`${listId}-opt-${index}`}
                      role="option"
                      aria-selected={index === activeIndex}
                      onClick={() => handleSelect(location)}
                      className={`flex w-full items-start justify-between gap-3 px-4 py-3 text-left text-sm hover:bg-slate-100 ${
                        index === activeIndex ? "bg-slate-100" : ""
                      }`}
                    >
                      <span>
                        <span className="block font-medium text-slate-900">
                          {location.display_name}
                        </span>
                        {location.region_id && (
                          <span className="block text-[10px] uppercase tracking-wide text-slate-500">
                            region {location.region_id}
                          </span>
                        )}
                      </span>
                      <span className="text-xs uppercase tracking-wide text-slate-500">
                        {location.place_type || "place"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </form>
    </div>
  );
}
