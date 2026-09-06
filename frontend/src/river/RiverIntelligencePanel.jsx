import ProvenanceBadge from "../platform/ProvenanceBadge";

function Field({ label, value }) {
  const missing = value == null || value === "";
  return (
    <p className="text-[11px] text-slate-300">
      <span className="text-slate-500">{label}: </span>
      {missing ? "UNAVAILABLE" : String(value)}
    </p>
  );
}

export default function RiverIntelligencePanel({
  overview,
  segment,
  neighbors,
  observations,
  risk,
  onOpenForecast,
  onOpenScenario,
  onOpenExplore,
  onSelectNeighbor,
}) {
  const river = overview?.river || segment?.river;
  const level = observations?.current_water_level_m;
  const discharge = observations?.current_discharge_m3s;
  const threshold = observations?.flood_threshold_m;
  const roc = observations?.rate_of_change_level;
  return (
    <aside className="space-y-3 text-slate-200" aria-label="Selected river intelligence">
      <div className="sr-only" aria-live="polite">
        {river
          ? `River ${river.name || river.id}. Water level ${level == null ? "UNAVAILABLE" : level}. Discharge ${discharge == null ? "UNAVAILABLE" : discharge}. Flow direction ${overview?.flow_direction_status || "UNAVAILABLE / TOPOLOGY ONLY"}.`
          : "No river selected."}
      </div>
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">River intelligence</h2>
      <section>
        <h3 className="text-[11px] font-semibold uppercase text-slate-500">Overview</h3>
        <Field label="River" value={river?.name || river?.id} />
        <Field label="Segments" value={overview?.segment_count} />
        <Field label="Geometry" value={overview?.geometry_available ? "available (fixture)" : null} />
        <Field label="Observation status" value={overview?.observation_status} />
        <Field label="Forecast status" value={overview?.forecast_status} />
        <Field label="Flow direction" value={overview?.flow_direction_status} />
        <Field label="Source" value={overview?.source} />
        <Field label="Timestamp" value={overview?.timestamp} />
        <ProvenanceBadge status={overview?.provenance?.data_status || "DEMO"} freshness={overview?.freshness} />
      </section>
      <section>
        <h3 className="text-[11px] font-semibold uppercase text-slate-500">Selected segment</h3>
        {segment?.segment ? (
          <>
            <Field label="Segment ID" value={segment.segment.id} />
            <Field label="River" value={segment.river?.name} />
            <Field label="Geometry" value={segment.segment.geometry ? "LineString" : null} />
            <Field
              label="Upstream"
              value={(segment.upstream || []).map((row) => row.id).join(", ") || "none listed"}
            />
            <Field
              label="Downstream"
              value={(segment.downstream || []).map((row) => row.id).join(", ") || "none listed"}
            />
            <p className="text-[10px] text-slate-500">{segment.kind}. {segment.flow_direction_status}</p>
          </>
        ) : (
          <p className="text-[11px] text-slate-400">No segment selected.</p>
        )}
      </section>
      <section>
        <h3 className="text-[11px] font-semibold uppercase text-slate-500">Network vs hydrology</h3>
        <p className="text-[11px] text-slate-300">NETWORK PROPAGATION: topology walk of downstream-connected segments.</p>
        <p className="text-[11px] text-slate-300">HYDROLOGICAL PROPAGATION: NOT_COMPUTED</p>
        <p className="text-[11px] text-slate-300">ESTIMATED ARRIVAL TIME: UNAVAILABLE</p>
        <ul className="mt-1 max-h-24 overflow-y-auto text-[11px]">
          {(neighbors?.reachable_downstream || []).map((row) => (
            <li key={row.id}>
              <button type="button" className="text-sky-300 underline" onClick={() => onSelectNeighbor?.(row)}>
                {row.id}
              </button>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h3 className="text-[11px] font-semibold uppercase text-slate-500">Observations</h3>
        <p className="text-[11px]">WATER LEVEL: {level == null ? "UNAVAILABLE" : `${level} m`}</p>
        <p className="text-[11px]">DISCHARGE: {discharge == null ? "UNAVAILABLE" : `${discharge} m³/s`}</p>
        <p className="text-[11px]">FLOOD THRESHOLD: {threshold == null ? "UNAVAILABLE" : `${threshold} m`}</p>
        <p className="text-[11px]">CURRENT: {level == null ? "UNAVAILABLE" : `${level} m`}</p>
        <p className="text-[11px]">TIME TO THRESHOLD: UNAVAILABLE</p>
        <p className="text-[11px]">
          RATE OF CHANGE:{" "}
          {roc?.value != null && (roc?.status === "REAL" || roc?.status === "DEMO")
            ? `${Number(roc.value).toFixed(4)} ${roc.units} (interval ${roc.interval})`
            : "UNAVAILABLE"}
        </p>
        {roc?.reason && <p className="text-[10px] text-slate-500">{roc.reason}</p>}
        <ProvenanceBadge status={observations?.provenance?.data_status || "UNAVAILABLE"} />
      </section>
      <section>
        <h3 className="text-[11px] font-semibold uppercase text-slate-500">Downstream-connected area</h3>
        <p className="text-[10px] text-slate-500">STUDY REGION (city-registry bounds, not an administrative district)</p>
        {(overview?.study_regions || segment?.study_regions || []).length ? (
          (overview?.study_regions || segment?.study_regions || []).map((region) => (
            <p key={region.city_id} className="text-[11px] text-slate-300">
              {region.name} · {region.kind}
            </p>
          ))
        ) : (
          <p className="text-[11px] text-slate-400">No study-region intersection listed.</p>
        )}
        <p className="text-[10px] text-slate-500">
          Risk nearby is associated with a downstream-connected area, not a verified river cause.
        </p>
        <Field label="Connected risk" value={risk?.category} />
      </section>
      <div className="flex flex-col gap-1">
        {onOpenForecast && (
          <button type="button" onClick={onOpenForecast} className="text-left text-[11px] text-sky-300 underline">
            Open Forecast
          </button>
        )}
        {onOpenScenario && (
          <button type="button" onClick={onOpenScenario} className="text-left text-[11px] text-sky-300 underline">
            Open Scenario
          </button>
        )}
        {onOpenExplore && (
          <button type="button" onClick={onOpenExplore} className="text-left text-[11px] text-sky-300 underline">
            Return to Explore
          </button>
        )}
        <p className="text-[10px] text-amber-200">
          river_level_delta_m is recorded on scenarios; physical river-boundary coupling is not enabled.
        </p>
      </div>
    </aside>
  );
}
