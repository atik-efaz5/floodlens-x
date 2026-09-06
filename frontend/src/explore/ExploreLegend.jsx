import ProvenanceBadge from "../platform/ProvenanceBadge";

const RISK = [
  { id: "LOW", className: "bg-emerald-500" },
  { id: "MODERATE", className: "bg-yellow-400" },
  { id: "HIGH", className: "bg-orange-500" },
  { id: "CRITICAL", className: "bg-red-500" },
];

const INFRA = [
  { id: "hospital", label: "Hospital", color: "#ef4444" },
  { id: "school", label: "School", color: "#eab308" },
  { id: "bridge", label: "Bridge", color: "#38bdf8" },
  { id: "road", label: "Road geometry", color: "#64748b" },
  { id: "shelter", label: "Shelter", color: "#22c55e" },
  { id: "emergency", label: "Critical", color: "#a855f7" },
  { id: "river", label: "River", color: "#0ea5e9" },
];

export default function ExploreLegend({ layers, floodAvailable, catalogLegend }) {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-[11px] text-slate-200" aria-label="Map legend">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Legend</h3>
      <p className="mb-2 text-[10px] text-slate-500">Risk colors are not reused for infrastructure or flood depth.</p>
      <div className="mb-2">
        <p className="mb-1 font-medium text-slate-300">Risk</p>
        <ul className="space-y-1">
          {RISK.map((row) => (
            <li key={row.id} className="flex items-center gap-2">
              <span className={`inline-block h-2.5 w-2.5 rounded-sm ${row.className}`} aria-hidden />
              {row.id}
              {catalogLegend?.[row.id] ? <span className="text-slate-500">({catalogLegend[row.id]})</span> : null}
            </li>
          ))}
        </ul>
      </div>
      <div className="mb-2">
        <p className="mb-1 font-medium text-slate-300">Infrastructure</p>
        <ul className="space-y-1">
          {INFRA.filter((row) => {
            if (row.id === "river") return layers.rivers;
            if (row.id === "road") return layers.roads;
            if (row.id === "hospital") return layers.hospitals;
            if (row.id === "school") return layers.schools;
            if (row.id === "bridge") return layers.bridges;
            if (row.id === "shelter") return layers.shelters;
            if (row.id === "emergency") return layers.critical;
            return true;
          }).map((row) => (
            <li key={row.id} className="flex items-center gap-2">
              <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: row.color }} aria-hidden />
              {row.label}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <p className="mb-1 font-medium text-slate-300">Flood</p>
        {floodAvailable ? (
          <p className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-6 rounded-sm bg-sky-300/80" aria-hidden />
            Physics/scenario overlay (not a validated AI map)
          </p>
        ) : (
          <p className="text-slate-400">
            Flood overlay <ProvenanceBadge status="UNAVAILABLE" />
          </p>
        )}
      </div>
    </section>
  );
}
