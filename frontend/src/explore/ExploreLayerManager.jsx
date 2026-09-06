import { useEffect, useState } from "react";

import { fetchLayerCatalog } from "../platform/api";
import ProvenanceBadge from "../platform/ProvenanceBadge";
import ExploreLegend from "./ExploreLegend";

const TOGGLEABLE = [
  { key: "rivers", catalogId: "rivers", label: "Rivers" },
  { key: "roads", catalogId: "roads", label: "Roads" },
  { key: "hospitals", catalogId: "hospitals", label: "Hospitals" },
  { key: "schools", catalogId: "schools", label: "Schools" },
  { key: "bridges", catalogId: "bridges", label: "Bridges" },
  { key: "critical", catalogId: "critical_infrastructure", label: "Critical infrastructure" },
  { key: "shelters", catalogId: "shelters", label: "Shelters" },
];

function catalogRow(catalog, id) {
  return (catalog?.layers || []).find((row) => row.id === id);
}

function LayerRow({ title, status, reason, source, timestamp, freshness, enabled, onToggle, disabled, spatial, temporal }) {
  return (
    <div className="border-b border-slate-800/80 py-2 last:border-0">
      <label className="flex items-start justify-between gap-2">
        <span className="text-xs text-slate-100">{title}</span>
        <input
          type="checkbox"
          checked={Boolean(enabled) && !disabled}
          disabled={disabled}
          onChange={() => onToggle?.()}
          aria-label={`Toggle ${title}`}
        />
      </label>
      <div className="mt-1 flex flex-wrap items-center gap-1">
        <ProvenanceBadge status={status} freshness={freshness} />
      </div>
      {disabled && (
        <p className="mt-1 text-[10px] text-slate-400">
          UNAVAILABLE{reason ? `. Reason: ${reason}` : "."}
        </p>
      )}
      {!disabled && (
        <p className="mt-1 text-[10px] text-slate-500">
          source {source || "UNAVAILABLE"} · {timestamp || "UNAVAILABLE"}
          {spatial ? ` · ${spatial}` : ""}
          {temporal ? ` · ${temporal}` : ""}
        </p>
      )}
    </div>
  );
}

export default function ExploreLayerManager({
  cityId,
  layers,
  onChange,
  floodAvailable,
  forecastAvailable,
}) {
  const [catalog, setCatalog] = useState(null);

  useEffect(() => {
    if (!cityId) {
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
  }, [cityId]);

  const row = (id) => catalogRow(catalog, id);
  const catalogLoaded = Boolean(catalog);
  const flood = row("flood_extent");
  const forecast = row("predicted_flood");
  const rainfall = row("rainfall");
  const terrain = row("terrain");
  const population = row("population");
  const depth = row("water_depth");
  const level = row("water_level");
  const spatial = row("ai_spatial");
  const historical = row("flood_extent");

  return (
    <section className="space-y-3 text-slate-200" aria-label="Layer control">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Layers</h2>
      <LayerRow
        title="Current flood extent"
        status={floodAvailable ? flood?.data_status || "PARTIAL" : "UNAVAILABLE"}
        reason={flood?.reason || "No completed physics flood raster is attached."}
        source={flood?.source}
        timestamp={flood?.timestamp}
        freshness={flood?.freshness}
        enabled={layers.floodExtent && floodAvailable}
        disabled={!floodAvailable}
        onToggle={() => onChange({ ...layers, floodExtent: !layers.floodExtent })}
        spatial={flood?.spatial_resolution}
        temporal={flood?.temporal_resolution}
      />
      <LayerRow
        title="Forecast overlay"
        status={forecastAvailable ? forecast?.data_status || "DEMO" : "UNAVAILABLE"}
        reason="Heuristic/physics overlay only when an artifact exists. Not a validated spatial AI map."
        source={forecast?.source}
        timestamp={forecast?.timestamp}
        freshness={forecast?.freshness}
        enabled={layers.forecast && forecastAvailable}
        disabled={!forecastAvailable}
        onToggle={() => onChange({ ...layers, forecast: !layers.forecast })}
      />
      {TOGGLEABLE.map((item) => {
        const meta = row(item.catalogId);
        const unavailable =
          catalogLoaded && (meta?.data_status || "UNAVAILABLE") === "UNAVAILABLE";
        return (
          <LayerRow
            key={item.key}
            title={item.label}
            status={meta?.data_status || "UNAVAILABLE"}
            reason={meta?.reason}
            source={meta?.source}
            timestamp={meta?.timestamp}
            freshness={meta?.freshness}
            enabled={layers[item.key]}
            disabled={unavailable}
            onToggle={() => onChange({ ...layers, [item.key]: !layers[item.key] })}
            spatial={meta?.spatial_resolution}
            temporal={meta?.temporal_resolution}
          />
        );
      })}
      <LayerRow
        title="Rainfall"
        status={rainfall?.data_status || "UNAVAILABLE"}
        reason={rainfall?.reason || "No validated spatial rainfall layer is currently configured."}
        source={rainfall?.source}
        timestamp={rainfall?.timestamp}
        freshness={rainfall?.freshness}
        enabled={layers.rainfall && (rainfall?.data_status || "UNAVAILABLE") !== "UNAVAILABLE"}
        disabled={!catalogLoaded || (rainfall?.data_status || "UNAVAILABLE") === "UNAVAILABLE"}
        onToggle={() => onChange({ ...layers, rainfall: !layers.rainfall })}
        temporal={rainfall?.temporal_resolution}
      />
      <LayerRow
        title="Terrain / DEM preview"
        status={terrain?.data_status || "UNAVAILABLE"}
        reason={terrain?.reason || "Terrain raster is UNAVAILABLE."}
        source={terrain?.source}
        timestamp={terrain?.timestamp}
        freshness={terrain?.freshness}
        enabled={layers.terrain && (terrain?.data_status || "UNAVAILABLE") !== "UNAVAILABLE"}
        disabled={!catalogLoaded || (terrain?.data_status || "UNAVAILABLE") === "UNAVAILABLE"}
        onToggle={() => onChange({ ...layers, terrain: !layers.terrain })}
      />
      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-2">
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Unavailable rasters</p>
        {[rainfall, terrain, population, depth, level, spatial]
          .filter(Boolean)
          .filter((meta) => (meta.data_status || "UNAVAILABLE") === "UNAVAILABLE")
          .map((meta) => (
          <p key={meta.id} className="mb-2 text-[11px] text-slate-300">
            {meta.title} <ProvenanceBadge status="UNAVAILABLE" />
            <span className="mt-0.5 block text-[10px] text-slate-500">
              Reason: {meta.reason || "This layer is not configured."}
            </span>
          </p>
        ))}
        {population && (population.data_status || "UNAVAILABLE") !== "UNAVAILABLE" && (
          <p className="mb-2 text-[11px] text-slate-300">
            {population.title} <ProvenanceBadge status={population.data_status} />
            <span className="mt-0.5 block text-[10px] text-slate-500">
              Reason: {population.reason || "DEMO totals. Not a census raster."}
            </span>
          </p>
        )}
        {level && (level.data_status || "UNAVAILABLE") !== "UNAVAILABLE" && (
          <p className="mb-2 text-[11px] text-slate-300">
            {level.title} <ProvenanceBadge status={level.data_status} />
            <span className="mt-0.5 block text-[10px] text-slate-500">
              Reason: {level.reason || "DEMO gauge series."}
            </span>
          </p>
        )}
        <p className="text-[11px] text-slate-300">
          Historical flood layer <ProvenanceBadge status={historical?.data_status === "UNAVAILABLE" ? "UNAVAILABLE" : "PARTIAL"} />
          <span className="mt-0.5 block text-[10px] text-slate-500">
            Reason: stored flood states only after a physics job. EMSR polygons are not downloaded.
          </span>
        </p>
      </div>
      <ExploreLegend layers={layers} floodAvailable={floodAvailable} catalogLegend={catalog?.legend} />
    </section>
  );
}
