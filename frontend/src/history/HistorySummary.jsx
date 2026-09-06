function Metric({ label, value }) {
  return (
    <p className="text-[11px] text-slate-300">
      <span className="text-slate-500">{label}: </span>
      {value == null || value === "" ? "UNAVAILABLE" : String(value)}
    </p>
  );
}

export default function HistorySummary({ detail, observation, compare }) {
  const event = detail?.event || {};
  const metrics = detail?.observation_metrics?.metrics;
  const compareRow = compare || detail?.compare || {};
  return (
    <section className="space-y-3 text-xs text-slate-200" aria-label="Historical event summary">
      <h2 className="font-semibold uppercase tracking-wide text-slate-400">Event</h2>
      <Metric label="event_id" value={event.event_id} />
      <Metric label="name" value={event.name} />
      <Metric label="start" value={event.start} />
      <Metric label="peak" value={event.peak} />
      <Metric label="end" value={event.end} />
      <Metric label="regions" value={(event.regions || []).join(", ")} />
      <Metric label="mechanism" value={event.flood_mechanism} />
      <Metric label="source" value={event.observation_source} />
      <Metric label="n_observations" value={event.n_observations} />
      <Metric label="data_status" value={event.data_status} />
      <Metric label="semantic_type" value={event.semantic_type} />

      <h2 className="font-semibold uppercase tracking-wide text-slate-400">Selected observation</h2>
      {!observation && <p className="text-amber-200">No observation selected.</p>}
      {observation && (
        <>
          <p className="rounded border border-emerald-900/60 bg-emerald-950/40 px-2 py-1 text-[10px] uppercase">
            OBSERVED
          </p>
          <Metric label="timestamp" value={observation.timestamp} />
          <Metric label="source" value={observation.source} />
          <Metric label="resolution" value={observation.resolution_m} />
          <Metric label="dataset version" value={observation.dataset_version} />
          <Metric label="valid coverage" value={observation.valid_coverage} />
          <Metric label="unknown coverage" value={observation.unknown_coverage} />
          <Metric label="n_flood" value={observation.flood_extent?.n_flood} />
          <Metric label="n_unknown" value={observation.flood_extent?.n_unknown} />
          <p className="text-[10px] text-slate-500">{observation.resolution_note || "Unknown pixels remain unknown."}</p>
        </>
      )}

      <h2 className="font-semibold uppercase tracking-wide text-slate-400">Observed transitions</h2>
      {!metrics && <p className="text-amber-200">{detail?.observation_metrics?.reason || "UNAVAILABLE"}</p>}
      {metrics && (
        <>
          <Metric label="flood area t0 px" value={metrics.flood_area_t0_pixels} />
          <Metric label="flood area t1 px" value={metrics.flood_area_t1_pixels} />
          <Metric label="newly flooded px" value={metrics.newly_flooded_area_pixels} />
          <Metric label="receding px" value={metrics.receding_area_pixels} />
          <Metric label="persistent flood px" value={metrics.persistent_flooded_area_pixels} />
          <Metric label="valid coverage" value={metrics.valid_coverage} />
          <Metric label="unknown coverage" value={metrics.unknown_coverage} />
          <p className="text-[10px] text-slate-500">Descriptive observation metrics, not forecast skill.</p>
        </>
      )}

      <h2 className="font-semibold uppercase tracking-wide text-slate-400">Forecast vs reality</h2>
      <Metric label="COMPARISON" value={compareRow.comparison} />
      <p className="text-[11px] text-amber-200">{compareRow.reason || compareRow.comparison_reason || ""}</p>
      <Metric label="depth comparison" value={compareRow.depth_comparison} />
      <p className="text-[10px] text-slate-500">
        Spatial AI: {detail?.spatial_ai?.status || "NOT_VALIDATED"}. Target B: {detail?.target_b?.status}.
      </p>
    </section>
  );
}
