export default function RiverTopologyGraph({
  segments,
  selectedSegmentId,
  onSelectSegment,
}) {
  const rows = segments || [];
  if (!rows.length) {
    return (
      <p className="text-[11px] text-slate-400">
        NETWORK TOPOLOGY unavailable until a river with segments is selected.
      </p>
    );
  }
  return (
    <section aria-label="Network topology">
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Network topology</h3>
      <p className="mb-2 text-[10px] text-slate-500">
        FLOW DIRECTION: UNAVAILABLE / TOPOLOGY ONLY. Not hydrological causality.
      </p>
      <ol className="space-y-1">
        <li className="text-[10px] uppercase tracking-wide text-slate-500">Upstream</li>
        {rows.map((segment) => {
          const active = segment.id === selectedSegmentId;
          return (
            <li key={segment.id}>
              <button
                type="button"
                onClick={() => onSelectSegment?.(segment)}
                className={`flex w-full items-center gap-2 rounded px-2 py-1 text-left text-[11px] ${
                  active ? "bg-amber-500/20 text-amber-100" : "text-slate-200 hover:bg-slate-800"
                }`}
              >
                <span aria-hidden className="text-slate-500">
                  ↓
                </span>
                {segment.id}
              </button>
            </li>
          );
        })}
        <li className="text-[10px] uppercase tracking-wide text-slate-500">Downstream-connected area</li>
      </ol>
    </section>
  );
}
