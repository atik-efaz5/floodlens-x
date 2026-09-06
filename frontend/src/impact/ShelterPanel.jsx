function Field({ label, value }) {
  return (
    <p className="text-[11px] text-slate-300">
      <span className="text-slate-500">{label}: </span>
      {value == null || value === "" ? "UNAVAILABLE" : String(value)}
    </p>
  );
}

export default function ShelterPanel({ shelters }) {
  const rows = shelters?.shelters || [];
  return (
    <section aria-label="Shelter analysis">
      <h3 className="text-[11px] font-semibold uppercase text-slate-500">Shelter analysis</h3>
      <Field label="CAPACITY" value={null} />
      <Field label="OCCUPANCY" value={null} />
      <Field label="ACCESSIBILITY" value="NOT_COMPUTED" />
      {rows.length === 0 && <p className="text-[11px] text-slate-400">No cataloged shelters in this region.</p>}
      <ul className="max-h-40 space-y-2 overflow-y-auto">
        {rows.map((row) => (
          <li key={row.id} className="rounded border border-slate-800 px-2 py-1">
            <p className="text-[11px] font-medium">{row.name}</p>
            <Field label="Location" value={row.latitude != null ? `${row.latitude}, ${row.longitude}` : null} />
            <Field label="Source" value={row.source} />
            <Field label="Flood exposure" value={row.exposure_status} />
            <Field label="Accessibility" value="UNAVAILABLE" />
            <Field label="Capacity" value={null} />
            <Field label="Occupancy" value={null} />
            <Field label="Suitability" value={row.suitability} />
            <p className="text-[10px] text-slate-500">{row.suitability_note}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
