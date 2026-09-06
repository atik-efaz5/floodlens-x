import { useEffect, useRef } from "react";

export default function HistoryTimeline({ observations, selectedId, onSelect, statusText }) {
  const rows = observations || [];
  const listRef = useRef(null);

  useEffect(() => {
    const node = listRef.current;
    if (!node) return undefined;
    const onKey = (event) => {
      if (!rows.length) return;
      const index = Math.max(0, rows.findIndex((row) => row.observation_id === selectedId));
      if (event.key === "ArrowRight" || event.key === "ArrowDown") {
        event.preventDefault();
        const next = rows[Math.min(rows.length - 1, index + 1)];
        onSelect?.(next);
      }
      if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
        event.preventDefault();
        const prev = rows[Math.max(0, index - 1)];
        onSelect?.(prev);
      }
    };
    node.addEventListener("keydown", onKey);
    return () => node.removeEventListener("keydown", onKey);
  }, [rows, selectedId, onSelect]);

  return (
    <section
      className="border-t border-slate-800 bg-slate-950/95 px-4 py-2 text-slate-100"
      aria-label="Historical observation timeline"
    >
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          Observed timeline (actual scene times)
        </h2>
        <p className="sr-only" aria-live="polite">
          {statusText || "No observation selected."}
        </p>
        <p className="text-[10px] text-slate-500">
          T-72h / T-48h / T-24h are not invented. Unknown pixels stay unknown.
        </p>
      </div>
      <div ref={listRef} tabIndex={0} className="flex flex-wrap gap-2 outline-none" role="list">
        {rows.map((row) => {
          const active = row.observation_id === selectedId;
          return (
            <button
              key={row.observation_id}
              type="button"
              onClick={() => onSelect?.(row)}
              className={`min-w-[8rem] rounded-lg border px-2 py-2 text-left ${
                active ? "border-sky-400 bg-sky-500/20" : "border-slate-800 bg-slate-900/70"
              }`}
            >
              <p className="text-xs font-semibold">{row.timestamp || "timestamp UNAVAILABLE"}</p>
              <p className="text-[10px] uppercase text-slate-400">{row.semantic_type || "OBSERVATION"}</p>
              <p className="text-[10px] text-slate-500">
                source {row.source || "UNAVAILABLE"} · {row.resolution_m != null ? `${row.resolution_m} m` : "resolution UNAVAILABLE"}
              </p>
              <p className="text-[10px] text-slate-500">
                overlay {row.overlay_available ? "available" : "UNAVAILABLE"}
              </p>
            </button>
          );
        })}
        {!rows.length && (
          <p className="text-[11px] text-amber-200">No observation timestamps for this event.</p>
        )}
      </div>
    </section>
  );
}
