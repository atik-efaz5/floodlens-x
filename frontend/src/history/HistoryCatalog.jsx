export default function HistoryCatalog({
  events,
  selectedId,
  onSelect,
  filters,
  onFilterChange,
  status,
}) {
  const rows = events || [];
  return (
    <section className="space-y-3" aria-label="Historical event catalog">
      <h1 className="text-lg font-semibold">History</h1>
      <p className="text-[11px] text-slate-400">
        Observation + audit. GFM labels use event_id; names are not invented. EMSR polygons were not downloaded.
      </p>
      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <label className="block">
          Year
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1"
            value={filters.year || ""}
            onChange={(event) => onFilterChange({ ...filters, year: event.target.value })}
            inputMode="numeric"
            aria-label="Filter by year"
          />
        </label>
        <label className="block">
          Region
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1"
            value={filters.region || ""}
            onChange={(event) => onFilterChange({ ...filters, region: event.target.value })}
            aria-label="Filter by region"
          />
        </label>
        <label className="block">
          Mechanism
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1"
            value={filters.flood_mechanism || ""}
            onChange={(event) => onFilterChange({ ...filters, flood_mechanism: event.target.value })}
            aria-label="Filter by flood mechanism"
          />
        </label>
        <label className="block">
          Source
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1"
            value={filters.source || ""}
            onChange={(event) => onFilterChange({ ...filters, source: event.target.value })}
            aria-label="Filter by observation source"
          />
        </label>
        <label className="block">
          Model
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1"
            value={filters.model || ""}
            onChange={(event) => onFilterChange({ ...filters, model: event.target.value })}
            aria-label="Filter by associated model"
          />
        </label>
        <label className="block">
          Status
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1"
            value={filters.status || ""}
            onChange={(event) => onFilterChange({ ...filters, status: event.target.value })}
            aria-label="Filter by data status"
          />
        </label>
      </div>
      {status === "loading" && <p className="text-[11px] text-slate-400">Loading catalog…</p>}
      {status === "error" && <p className="text-[11px] text-amber-200">Catalog UNAVAILABLE.</p>}
      <ul className="max-h-[28rem] space-y-2 overflow-y-auto" role="listbox" aria-label="Historical events">
        {rows.map((row) => {
          const active = row.event_id === selectedId;
          return (
            <li key={row.event_id}>
              <button
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => onSelect(row)}
                className={`w-full rounded-lg border px-2 py-2 text-left ${
                  active ? "border-sky-400 bg-sky-500/20" : "border-slate-800 bg-slate-900/70"
                }`}
              >
                <p className="text-xs font-semibold">{row.label || row.event_id}</p>
                <p className="text-[10px] text-slate-400">
                  {row.start || "start UNAVAILABLE"} → {row.end || "end UNAVAILABLE"}
                </p>
                <p className="text-[10px] text-slate-500">
                  {(row.regions || []).join(", ") || "region UNAVAILABLE"} · {row.flood_mechanism || "mechanism UNAVAILABLE"}
                </p>
                <p className="text-[10px] text-slate-500">
                  {row.n_observations ?? 0} observations · {row.data_status} · {row.catalog_family}
                </p>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
