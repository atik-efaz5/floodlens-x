import { useEffect, useState } from "react";

import { fetchRivers, fetchRiverState } from "./api";
import ProvenanceBadge from "./ProvenanceBadge";

function SeriesChart({ series }) {
  const points = (series || []).filter((row) => row.available && row.water_level_m != null);
  if (points.length < 2) {
    return <p className="text-xs text-slate-400">Not enough gauge points to chart.</p>;
  }
  const values = points.map((row) => Number(row.water_level_m));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 220;
  const height = 56;
  const d = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="mt-2 w-full text-sky-300" aria-label="Water level series">
      <path d={d} fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

export default function RiverForecastPanel({ riverId, cityId, visible }) {
  const [rivers, setRivers] = useState([]);
  const [selected, setSelected] = useState(riverId || "");
  const [state, setState] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!visible) {
      return undefined;
    }
    let cancelled = false;
    fetchRivers(cityId)
      .then((data) => {
        if (cancelled) {
          return;
        }
        const rows = data.data || data.rivers || [];
        setRivers(rows);
        if (!selected && rows[0]?.id) {
          setSelected(rows[0].id);
        }
        if (rows.length && riverId && rows.some((row) => row.id === riverId) && !selected) {
          setSelected(riverId);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRivers([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [cityId, visible]);

  useEffect(() => {
    if (!visible || !selected) {
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    fetchRiverState(selected)
      .then((data) => {
        if (!cancelled) {
          setState(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
          setState(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selected, visible]);

  if (!visible) {
    return null;
  }
  const graph = state?.graph || {};
  return (
    <section className="glass-panel mt-3 rounded-lg px-4 py-3 text-sm text-slate-200">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">River state</h2>
      <label className="mb-2 block text-[11px] text-slate-400">
        River
        <select
          value={selected}
          onChange={(event) => setSelected(event.target.value)}
          className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
        >
          {!rivers.length && <option value={riverId || "buriganga"}>{riverId || "buriganga"}</option>}
          {rivers.map((river) => (
            <option key={river.id} value={river.id}>
              {river.name || river.id}
            </option>
          ))}
        </select>
      </label>
      {loading && <p className="text-xs text-slate-400">Loading river graph…</p>}
      {error && <p className="text-xs text-amber-200">River status unavailable: {error}</p>}
      {!loading && !error && !state && <p className="text-xs text-slate-400">No river selected.</p>}
      {state && (
        <>
          <ProvenanceBadge
            status={state.provenance?.data_status || "UNAVAILABLE"}
            freshness={state.provenance?.freshness}
          />
          <p className="mt-2 text-xs">
            WATER LEVEL: {state.current?.water_level_m == null ? "UNAVAILABLE" : `${state.current.water_level_m} m`}
          </p>
          <p className="text-xs">
            DISCHARGE: {state.current?.discharge_m3s == null ? "UNAVAILABLE" : `${state.current.discharge_m3s} m³/s`}
          </p>
          <p className="mt-1 text-xs text-slate-400">trend {state.trend || "UNAVAILABLE"}</p>
          <p className="mt-1 text-xs text-slate-400">{state.forecast?.reason}</p>
          <p className="mt-1 text-[11px] text-slate-500">
            graph nodes {graph.nodes?.length ?? 0} · segments {graph.edges?.length ?? 0}
          </p>
          <p className="text-[11px] text-slate-500">
            upstream {(state.upstream?.nodes || []).join(", ") || "UNAVAILABLE"} · downstream{" "}
            {(state.downstream?.nodes || []).join(", ") || "UNAVAILABLE"}
          </p>
          <p className="text-[11px] text-slate-500">{state.upstream?.note}</p>
          <SeriesChart series={state.series} />
        </>
      )}
    </section>
  );
}
