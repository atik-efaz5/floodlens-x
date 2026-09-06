import { useEffect, useState } from "react";

import { fetchLayerCatalog } from "./api";
import ProvenanceBadge from "./ProvenanceBadge";

export default function LayerLegend({
  cityId,
  visible,
  showForecast,
  onToggleForecast,
  showRainfall,
  onToggleRainfall,
  rainfallStatus,
  rainfallSummary,
  showRivers = true,
  onToggleRivers,
  showTerrain = false,
  onToggleTerrain,
  osmFilter,
  onOsmFilter,
}) {
  const [catalog, setCatalog] = useState(null);

  useEffect(() => {
    if (!visible || !cityId) {
      return undefined;
    }
    let cancelled = false;
    fetchLayerCatalog(cityId)
      .then((data) => {
        if (!cancelled) {
          setCatalog(data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCatalog(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [cityId, visible]);

  if (!visible) {
    return null;
  }

  const layer = (id) => (catalog?.layers || []).find((row) => row.id === id);

  return (
    <section className="pointer-events-auto absolute left-4 top-16 z-[1100] max-h-72 w-64 overflow-y-auto rounded-lg border border-white/15 bg-slate-900/90 p-3 text-xs text-white backdrop-blur">
      <h2 className="mb-2 font-semibold uppercase tracking-wide text-slate-300">Layers / legend</h2>
      {(catalog?.layers || []).map((row) => (
        <div key={row.id} className="mb-1 flex items-center justify-between gap-2">
          <span>{row.title || row.id}</span>
          <ProvenanceBadge status={row.data_status} />
        </div>
      ))}
      <div className="mt-2 space-y-1 border-t border-slate-700 pt-2">
        <label className="flex items-center justify-between">
          <span>Forecast overlay</span>
          <input type="checkbox" checked={Boolean(showForecast)} onChange={() => onToggleForecast?.()} aria-label="Toggle forecast overlay" />
        </label>
        <label className="flex items-center justify-between">
          <span>Rainfall</span>
          <input
            type="checkbox"
            checked={Boolean(showRainfall)}
            onChange={() => onToggleRainfall?.()}
            disabled={(layer("rainfall")?.data_status || rainfallStatus) === "UNAVAILABLE"}
            aria-label="Toggle rainfall observations"
          />
        </label>
        {(layer("rainfall")?.data_status || rainfallStatus) === "UNAVAILABLE" ? (
          <p className="text-[10px] text-slate-400">RAINFALL: UNAVAILABLE</p>
        ) : (
          <p className="text-[10px] text-slate-400">
            RAINFALL: {layer("rainfall")?.data_status || rainfallStatus} — not a radar grid
          </p>
        )}
        <label className="flex items-center justify-between">
          <span>Rivers</span>
          <input
            type="checkbox"
            checked={Boolean(showRivers)}
            onChange={() => onToggleRivers?.()}
            aria-label="Toggle river network"
          />
        </label>
        {(layer("rivers")?.data_status || "UNAVAILABLE") === "UNAVAILABLE" && (
          <p className="text-[10px] text-slate-400">RIVERS: UNAVAILABLE</p>
        )}
        {(layer("terrain")?.data_status || "UNAVAILABLE") === "UNAVAILABLE" ? (
          <p className="text-[10px] text-slate-400">TERRAIN: UNAVAILABLE</p>
        ) : (
          <>
            <label className="flex items-center justify-between">
              <span>Terrain preview</span>
              <input
                type="checkbox"
                checked={Boolean(showTerrain)}
                onChange={() => onToggleTerrain?.()}
                aria-label="Toggle terrain preview"
              />
            </label>
            <p className="text-[10px] text-slate-400">
              TERRAIN: {layer("terrain")?.data_status} hillshade preview — not a solver DEM
            </p>
          </>
        )}
        {(layer("population")?.data_status || "UNAVAILABLE") === "UNAVAILABLE" && (
          <p className="text-[10px] text-slate-400">POPULATION: UNAVAILABLE</p>
        )}
        {showRainfall && rainfallSummary && (
          <p className="text-[10px] text-slate-300">
            Latest precip {rainfallSummary.value_mm == null ? "UNAVAILABLE" : `${rainfallSummary.value_mm} mm`} ·{" "}
            {rainfallSummary.observed_at || "no timestamp"}
          </p>
        )}
        <label className="mt-1 flex items-center gap-2">
          OSM type
          <select
            value={osmFilter}
            onChange={(event) => onOsmFilter?.(event.target.value)}
            aria-label="Infrastructure type filter"
            className="rounded border border-slate-600 bg-slate-800 px-1 py-0.5"
          >
            {["", "hospital", "school", "clinic", "shelter", "emergency", "bridge", "road"].map((option) => (
              <option key={option || "all"} value={option}>
                {option || "all"}
              </option>
            ))}
          </select>
        </label>
      </div>
    </section>
  );
}
