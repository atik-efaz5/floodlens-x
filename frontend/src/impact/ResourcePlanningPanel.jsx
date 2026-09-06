function Field({ label, value }) {
  return (
    <p className="text-[11px] text-slate-300">
      <span className="text-slate-500">{label}: </span>
      {value == null || value === "" ? "UNAVAILABLE" : String(value)}
    </p>
  );
}

export default function ResourcePlanningPanel({ resources, allowed }) {
  if (!allowed) {
    return (
      <p className="text-[11px] text-slate-400">
        Resource planning: UNAVAILABLE for this role (resources.read).
      </p>
    );
  }
  const inventory = resources?.inventory || {};
  return (
    <section aria-label="Resource planning">
      <h3 className="text-[11px] font-semibold uppercase text-slate-500">Resource planning</h3>
      <p className="text-[10px] text-slate-500">
        OBSERVED RESOURCE INVENTORY vs PLANNING ESTIMATE. DEMO inventories are labeled DEMO, never REAL.
      </p>
      {Object.entries(inventory).map(([key, row]) => (
        <Field key={key} label={`${key} (${row.kind})`} value={row.status === "UNAVAILABLE" ? null : row.value} />
      ))}
      <Field label="Planning estimates" value={resources?.planning_estimates?.status} />
      {(resources?.priorities || []).map((row, index) => (
        <div key={index} className="mt-2 rounded border border-slate-800 px-2 py-1">
          <Field label="Priority" value={row.priority} />
          <p className="text-[11px]">WHAT: {row.what}</p>
          <p className="text-[11px]">WHY: {row.why}</p>
          <p className="text-[11px]">EVIDENCE: {typeof row.evidence === "string" ? row.evidence : JSON.stringify(row.evidence)}</p>
          <p className="text-[10px] text-slate-500">LIMITATIONS: {row.limitations}</p>
          <Field label="Data status" value={row.data_status} />
        </div>
      ))}
    </section>
  );
}
