import { useEffect, useState } from "react";

import ProvenanceBadge from "../platform/ProvenanceBadge";
import { fetchFloodStates } from "../platform/api";

export default function ExploreTimeline({
  cityId,
  forecast,
  selectedTime,
  onSelectTime,
}) {
  const [states, setStates] = useState([]);
  const [status, setStatus] = useState("idle");

  useEffect(() => {
    if (!cityId) {
      setStates([]);
      return undefined;
    }
    let cancelled = false;
    setStatus("loading");
    fetchFloodStates(cityId)
      .then((data) => {
        if (cancelled) {
          return;
        }
        const rows = data.data || [];
        setStates(rows);
        setStatus(rows.length ? "ok" : "empty");
      })
      .catch(() => {
        if (!cancelled) {
          setStates([]);
          setStatus("error");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [cityId]);

  const heuristic = (forecast?.horizons || []).filter((row) => row.horizon_hours != null);

  return (
    <section className="border-t border-slate-800 bg-slate-950/95 px-4 py-2 text-slate-100" aria-label="Explore timeline">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          Timeline (observed and DEMO only)
        </h2>
        <p className="text-[10px] text-slate-500">
          Spatial AI 6–72h maps are UNAVAILABLE. Heuristic hours are DEMO, not operational inundation.
        </p>
      </div>
      {status === "loading" && <p className="text-[11px] text-slate-400">Loading time-indexed states…</p>}
      {status === "error" && <p className="text-[11px] text-amber-200">Could not load flood states.</p>}
      <div className="flex flex-wrap gap-2">
        {states.map((row) => {
          const key = row.t || row.observed_at || row.horizon_hours || row.id;
          const active = selectedTime === key;
          return (
            <button
              key={String(key)}
              type="button"
              onClick={() => onSelectTime?.(key, row)}
              className={`min-w-[7rem] rounded-lg border px-2 py-2 text-left ${
                active ? "border-sky-400 bg-sky-500/20" : "border-slate-800 bg-slate-900/70"
              }`}
            >
              <p className="text-xs font-semibold">{row.observed_at || row.t || "observed"}</p>
              <ProvenanceBadge status={row.data_status || "PARTIAL"} />
              <p className="mt-1 text-[10px] text-slate-400">stored flood state</p>
            </button>
          );
        })}
        {heuristic.map((row) => (
          <div
            key={`demo-${row.horizon_hours}`}
            className="min-w-[7rem] rounded-lg border border-amber-500/30 bg-slate-900/70 px-2 py-2"
          >
            <p className="text-xs font-semibold">Heuristic {row.horizon_hours}h</p>
            <ProvenanceBadge status="DEMO" />
            <p className="mt-1 text-[10px] text-amber-200">DEMO / not spatial AI</p>
          </div>
        ))}
        {!states.length && !heuristic.length && status !== "loading" && (
          <p className="text-[11px] text-slate-400">No time-indexed flood states stored for this region.</p>
        )}
        <div className="min-w-[7rem] rounded-lg border border-slate-800 bg-slate-900/70 px-2 py-2">
          <p className="text-xs font-semibold">Spatial AI</p>
          <ProvenanceBadge status="UNAVAILABLE" />
          <p className="mt-1 text-[10px] text-slate-400">NOT_VALIDATED</p>
        </div>
      </div>
    </section>
  );
}
