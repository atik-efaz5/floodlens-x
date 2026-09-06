function Field({ label, value }) {
  return (
    <p className="text-[11px] text-slate-300">
      <span className="text-slate-500">{label}: </span>
      {value == null || value === "" ? "UNAVAILABLE" : String(value)}
    </p>
  );
}

export default function EvacuationPanel({ evacuation }) {
  return (
    <section aria-label="Potential evacuation-risk analysis">
      <h3 className="text-[11px] font-semibold uppercase text-slate-500">
        Potential evacuation-risk analysis
      </h3>
      <p className="text-[10px] text-amber-200">
        Planning support. Not an official evacuation order. Review with official emergency guidance.
      </p>
      <Field label="Kind" value={evacuation?.kind} />
      <Field label="Planning boundary" value={evacuation?.planning_boundary?.kind} />
      <Field label="Current risk category" value={evacuation?.current_risk_category} />
      <p className="text-[10px] text-slate-500">{evacuation?.current_risk_note}</p>
      <Field label="Routes" value={evacuation?.routes?.status} />
      <p className="text-[10px] text-slate-500">{evacuation?.routes?.reason}</p>
      {(evacuation?.routes?.features || []).map((route) => (
        <p key={route.id} className="text-[11px] text-slate-300">
          {route.name || route.id}: {route.kind || "DEMO"} polyline
        </p>
      ))}
      <Field label="Road accessibility" value={evacuation?.road_accessibility?.status} />
      <p className="text-[10px] text-slate-500">{evacuation?.road_accessibility?.reason}</p>
      <Field label="Travel time" value={null} />
      <Field label="Safe route" value={null} />
    </section>
  );
}
