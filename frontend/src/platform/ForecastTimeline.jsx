import { useEffect, useState } from "react";

import ProvenanceBadge from "./ProvenanceBadge";
import { fetchFloodStates } from "./api";

const HORIZONS = [6, 12, 24, 48, 72];

function classifyHorizon(point, product) {
  if (product?.model_kind === "PHYSICS_BASELINE" && point?.artifact_id) {
    return {
      ui: "PARTIAL",
      reason: "Physics SWE burst overlay — not a 6–72h inundation map.",
    };
  }
  if (point && (point.expected_depth == null || point.expected_depth === undefined)) {
    return {
      ui: product?.data_status || "DEMO",
      reason: "Meteorological-hour heuristic. Not a validated spatial flood map. Spatial AI 6–72h maps UNAVAILABLE.",
    };
  }
  if (!point) {
    return {
      ui: "UNAVAILABLE",
      reason: "No forecast point for this horizon. Spatial AI maps are UNAVAILABLE.",
    };
  }
  return { ui: point.data_status || product?.data_status || "DEMO", reason: product?.disclaimer };
}

export default function ForecastTimeline({ forecast, horizon, onHorizonChange, cityId }) {
  const product = forecast;
  const [states, setStates] = useState([]);

  useEffect(() => {
    if (!cityId) {
      setStates([]);
      return undefined;
    }
    let cancelled = false;
    fetchFloodStates(cityId)
      .then((data) => {
        if (!cancelled) {
          setStates(data.data || []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStates([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [cityId]);

  return (
    <section
      className="border-t border-slate-800 bg-slate-950/95 px-4 py-2 text-slate-100"
      aria-label="Forecast and event timeline"
    >
      <div className="mb-1 flex items-center justify-between gap-2">
        <h2 className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          Forecast / event timeline
        </h2>
        <p className="text-[10px] text-slate-500">
          Hours are meteorological, not SWE seconds. Unsupported spatial maps stay labeled UNAVAILABLE.
          {states.length
            ? ` ${states.length} time-indexed flood state(s).`
            : " No time-indexed flood states stored."}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {HORIZONS.map((hours) => {
          const point = (product?.horizons || []).find((row) => row.horizon_hours === hours);
          const kind = classifyHorizon(point, product);
          const timed = states.find((row) => Number(row.horizon_hours) === hours);
          const active = horizon === hours;
          return (
            <button
              key={hours}
              type="button"
              onClick={() => onHorizonChange?.(hours)}
              className={`min-w-[4.5rem] rounded-lg border px-2 py-2 text-left ${
                active ? "border-sky-400 bg-sky-500/20" : "border-slate-800 bg-slate-900/70"
              }`}
            >
              <p className="text-xs font-semibold">T+{hours}h</p>
              <ProvenanceBadge status={timed ? timed.data_status || kind.ui : kind.ui} />
              <p className="mt-1 text-[10px] text-slate-400">
                {timed
                  ? "indexed state"
                  : point
                    ? `heuristic P ${point.flood_probability ?? "UNAVAILABLE"}`
                    : "unsupported"}
              </p>
            </button>
          );
        })}
        <div className="min-w-[7rem] rounded-lg border border-slate-800 bg-slate-900/70 px-2 py-2">
          <p className="text-xs font-semibold">Spatial AI</p>
          <ProvenanceBadge status="UNAVAILABLE" />
          <p className="mt-1 text-[10px] text-slate-400">NOT_VALIDATED</p>
        </div>
      </div>
    </section>
  );
}
