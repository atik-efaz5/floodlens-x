import { useEffect, useId, useState } from "react";

import { fetchRiverSearch } from "../platform/api";
import ProvenanceBadge from "../platform/ProvenanceBadge";

export default function RiverSearch({ cityId, onSelect }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [empty, setEmpty] = useState(false);
  const [active, setActive] = useState(0);
  const [note, setNote] = useState("");
  const listId = useId();

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setResults([]);
      setOpen(false);
      setEmpty(false);
      setError(null);
      return undefined;
    }
    const handle = window.setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const payload = await fetchRiverSearch(trimmed, cityId);
        setResults(payload.results || []);
        setNote(payload.note || "");
        setEmpty((payload.results || []).length === 0);
        setOpen(true);
        setActive(0);
      } catch (err) {
        setResults([]);
        setError(err.message);
        setOpen(true);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => window.clearTimeout(handle);
  }, [query, cityId]);

  const choose = (hit) => {
    setQuery(hit.display_name || hit.name || "");
    setOpen(false);
    onSelect?.(hit);
  };

  const onKeyDown = (event) => {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (!open || !results.length) {
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((current) => Math.min(current + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      choose(results[active]);
    }
  };

  return (
    <div className="relative">
      <label className="block text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        River search
        <input
          type="search"
          role="combobox"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="River, segment, or study region"
          aria-label="River search"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={listId}
          className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
        />
      </label>
      <div className="sr-only" aria-live="polite">
        {loading ? "Searching rivers" : ""}
        {empty ? "No rivers found" : ""}
        {error ? `River search error ${error}` : ""}
      </div>
      {open && (
        <div id={listId} role="listbox" className="mt-1 rounded-lg border border-slate-700 bg-slate-900 text-sm">
          {loading && <p className="px-3 py-2 text-slate-400">Searching…</p>}
          {error && <p className="px-3 py-2 text-amber-200">{error}</p>}
          {!loading && !error && empty && (
            <p className="px-3 py-2 text-slate-400">No rivers match. Basin catalog is UNAVAILABLE.</p>
          )}
          {results.map((hit, index) => (
            <button
              key={`${hit.kind}-${hit.id}-${index}`}
              type="button"
              role="option"
              aria-selected={index === active}
              onClick={() => choose(hit)}
              className={`flex w-full items-center justify-between px-3 py-2 text-left ${
                index === active ? "bg-slate-800" : ""
              }`}
            >
              <span>
                <span className="block text-slate-100">{hit.display_name}</span>
                <span className="text-[10px] uppercase text-slate-500">{hit.kind}</span>
              </span>
              <ProvenanceBadge status={hit.data_status || "DEMO"} />
            </button>
          ))}
          {note && <p className="border-t border-slate-800 px-3 py-2 text-[10px] text-slate-500">{note}</p>}
        </div>
      )}
    </div>
  );
}
