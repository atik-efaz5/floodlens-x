export default function ScenarioHistory({ history, selectedId, onSelect }) {
  const rows = history || [];
  return (
    <section aria-label="Recent scenarios">
      <h3 className="text-[11px] font-semibold uppercase text-slate-500">Recent scenarios</h3>
      {rows.length === 0 ? (
        <p className="text-[11px] text-slate-500">No saved scenarios for this region.</p>
      ) : (
        <ul className="max-h-40 overflow-y-auto text-[11px]">
          {rows.map((row) => {
            const id = row.job_id || row.id;
            return (
              <li key={id}>
                <button
                  type="button"
                  className={`w-full text-left ${selectedId === id ? "text-amber-200" : "text-sky-300 underline"}`}
                  onClick={() => onSelect(row)}
                >
                  {row.name || row.kind} · {row.city_id} · {row.created_at || "UNAVAILABLE"} · {String(row.status || "UNAVAILABLE").toUpperCase()} · {row.model_version || "UNAVAILABLE"}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
