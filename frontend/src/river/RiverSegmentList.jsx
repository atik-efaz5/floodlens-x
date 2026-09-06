export default function RiverSegmentList({ river, selectedSegmentId, onSelectSegment }) {
  const segments = river?.segments || [];
  if (!river) {
    return <p className="text-[11px] text-slate-400">Select a river to list segments.</p>;
  }
  return (
    <section aria-label="River segments">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Segments</h3>
      {segments.length === 0 && <p className="text-[11px] text-slate-400">No segments in this viewport.</p>}
      <ul className="max-h-48 space-y-1 overflow-y-auto">
        {segments.map((segment) => {
          const active = selectedSegmentId === segment.id;
          return (
            <li key={segment.id}>
              <button
                type="button"
                onClick={() => onSelectSegment?.(segment)}
                className={`w-full rounded-md border px-2 py-1 text-left text-[11px] ${
                  active ? "border-amber-400 bg-amber-500/15 text-amber-100" : "border-slate-800 bg-slate-900 text-slate-200"
                }`}
              >
                <span className="font-medium">{segment.id}</span>
                <span className="mt-0.5 block text-slate-500">
                  {segment.from_node} → {segment.to_node}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
