import ProvenanceBadge from "../platform/ProvenanceBadge";

function Field({ label, value }) {
  const missing = value == null || value === "";
  return (
    <p className="text-[11px] text-slate-300">
      <span className="text-slate-500">{label}: </span>
      {missing ? "UNAVAILABLE" : String(value)}
    </p>
  );
}

function Category({ name, row }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-900/60 px-2 py-1">
      <p className="text-[11px] font-medium capitalize text-slate-200">{name}</p>
      <p className="text-[11px] text-slate-400">{row?.status || "UNAVAILABLE"}</p>
      <p className="text-[11px]">
        Affected: {row?.affected == null ? "UNAVAILABLE" : row.affected}
      </p>
      <p className="text-[10px] text-slate-500">{row?.computation}</p>
      <p className="text-[10px] text-slate-500">{row?.reason}</p>
    </div>
  );
}

export default function ImpactSummaryPanel({ summary, role, selectedAsset, onSelectAsset, assets }) {
  const categories = summary?.categories || {};
  const population = categories.population;
  return (
    <aside className="space-y-3 text-slate-200" aria-label="Impact summary">
      <div className="sr-only" aria-live="polite">
        Population exposure {population?.affected == null ? "UNAVAILABLE" : population.affected}.
        Planning support only, not an official evacuation order.
      </div>
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Impact summary</h2>
      <p className="text-[10px] text-amber-200">
        Potential evacuation-risk analysis. Planning support. Review with official emergency guidance.
      </p>
      <Field label="Region" value={summary?.city_id} />
      <Field label="Scenario" value={summary?.scenario?.label} />
      <Field label="Job" value={summary?.scenario?.job_id} />
      <Field label="Timestamp" value={summary?.timestamp} />
      <ProvenanceBadge status={summary?.provenance?.data_status || "PARTIAL"} />
      <section>
        <h3 className="text-[11px] font-semibold uppercase text-slate-500">Population</h3>
        <p className="text-[11px]">
          {population?.affected == null
            ? "POPULATION EXPOSURE: UNAVAILABLE"
            : `POPULATION EXPOSURE: ${population.affected}`}
        </p>
        <p className="text-[10px] text-slate-500">
          {population?.reason || "No authoritative population dataset is currently configured."}
        </p>
      </section>
      <div className="grid grid-cols-2 gap-1">
        {["hospitals", "schools", "bridges", "roads", "shelters", "critical", "buildings", "agriculture"].map((key) => (
          <Category key={key} name={key} row={categories[key]} />
        ))}
      </div>
      {role === "researcher" && (
        <section>
          <h3 className="text-[11px] font-semibold uppercase text-slate-500">Computation</h3>
          <Field label="Raster attached" value={summary?.scenario?.available ? "yes" : "no"} />
          <Field label="Polygon masks" value="NOT_COMPUTED" />
          <p className="text-[10px] text-slate-500">{(summary?.assumptions || []).join(" ")}</p>
        </section>
      )}
      {role === "admin" && (
        <section>
          <h3 className="text-[11px] font-semibold uppercase text-slate-500">Pipeline</h3>
          <Field label="Artifact" value={summary?.scenario?.artifact_id} />
          <Field label="Job kind" value={summary?.scenario?.kind} />
          <p className="text-[10px] text-slate-500">Spatial AI remains NOT_VALIDATED. Inventories are not fabricated.</p>
        </section>
      )}
      <section>
        <h3 className="text-[11px] font-semibold uppercase text-slate-500">Assets</h3>
        <ul className="max-h-40 overflow-y-auto text-[11px]">
          {(assets || []).map((asset) => (
            <li key={asset.id}>
              <button
                type="button"
                className={`w-full text-left ${selectedAsset?.id === asset.id ? "text-amber-200" : "text-sky-300 underline"}`}
                onClick={() => onSelectAsset?.(asset)}
              >
                {asset.name || asset.id} · {asset.impact_status}
              </button>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}
