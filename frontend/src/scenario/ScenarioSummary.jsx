import ProvenanceBadge from "../platform/ProvenanceBadge";

function Cell({ label, value }) {
  const missing = value == null || value === "";
  return (
    <p className="text-[11px] text-slate-300">
      <span className="text-slate-500">{label}: </span>
      {missing ? "UNAVAILABLE" : String(value)}
    </p>
  );
}

function RiskBlock({ title, risk }) {
  if (!risk) {
    return (
      <div className="rounded-md border border-slate-800 bg-slate-900/60 px-2 py-1">
        <p className="text-[11px] font-medium text-slate-200">{title}</p>
        <p className="text-[11px] text-slate-500">NOT_COMPUTED</p>
      </div>
    );
  }
  return (
    <div className="rounded-md border border-slate-800 bg-slate-900/60 px-2 py-1">
      <p className="text-[11px] font-medium text-slate-200">{title}</p>
      <p className="text-[11px]">Flood probability P: {risk.probability ?? "UNAVAILABLE"}</p>
      <p className="text-[11px]">Exposure E: {risk.exposure ?? "UNAVAILABLE"} (city prior, not population)</p>
      <p className="text-[11px]">Severity S: {risk.severity ?? "UNAVAILABLE"}</p>
      <p className="text-[11px]">Score: {risk.score ?? "UNAVAILABLE"}</p>
    </div>
  );
}

export default function ScenarioSummary({
  cityName,
  workspace,
  baselineJob,
  scenarioJob,
  impact,
  mapMode,
  onMapMode,
}) {
  const compare = workspace?.compare;
  const a = (compare?.comparisons || [])[0];
  const b = (compare?.comparisons || [])[1];
  const diff = compare?.difference;
  const chain = workspace?.causal_chain?.links || [];
  return (
    <aside className="space-y-3 text-slate-200" aria-label="Scenario summary">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Scenario summary</h2>
      <Cell label="Region" value={cityName} />
      <Cell label="Baseline" value={baselineJob?.name || baselineJob?.id} />
      <Cell label="Scenario" value={scenarioJob?.name || scenarioJob?.id} />
      <Cell label="Status" value={scenarioJob?.status || baselineJob?.status} />
      <ProvenanceBadge status={workspace?.provenance?.data_status || "SIMULATED"} />
      <p className="text-[10px] text-amber-200">
        Physics results are SIMULATED. river_level_applied_to_solver = false. Solver coupling: NOT APPLIED.
      </p>
      <div className="flex flex-wrap gap-1">
        {[
          { id: "scenario", label: "Scenario map" },
          { id: "split", label: "Split baseline | scenario" },
          { id: "difference", label: "Difference" },
        ].map((mode) => (
          <button
            key={mode.id}
            type="button"
            aria-pressed={mapMode === mode.id}
            onClick={() => onMapMode(mode.id)}
            className={`rounded px-2 py-1 text-[10px] uppercase ${
              mapMode === mode.id ? "bg-flood-500 text-white" : "bg-slate-800 text-slate-200"
            }`}
          >
            {mode.label}
          </button>
        ))}
      </div>
      <section>
        <h3 className="text-[11px] font-semibold uppercase text-slate-500">Metrics</h3>
        <Cell label="Baseline max depth m" value={a?.max_depth_m} />
        <Cell label="Scenario max depth m" value={b?.max_depth_m} />
        <Cell label="Delta max depth m" value={diff?.max_depth_m} />
        <Cell label="Baseline flooded km²" value={a?.flooded_area_km2} />
        <Cell label="Scenario flooded km²" value={b?.flooded_area_km2} />
        <Cell label="Delta flooded km²" value={diff?.flooded_area_km2} />
        <Cell label="Applied rainfall m/s" value={b?.rainfall_rate_applied_mps} />
        <Cell label="Base rainfall m/s" value={b?.rainfall_rate_base_mps} />
        <p className="text-[11px]">
          {impact?.categories?.population?.affected == null
            ? "POPULATION EXPOSURE: UNAVAILABLE"
            : `POPULATION EXPOSURE: ${impact.categories.population.affected}`}
        </p>
      </section>
      <section>
        <h3 className="text-[11px] font-semibold uppercase text-slate-500">Risk comparison</h3>
        <div className="grid grid-cols-1 gap-1">
          <RiskBlock title="Baseline risk" risk={a?.risk} />
          <RiskBlock title="Scenario risk" risk={b?.risk} />
          <div className="rounded-md border border-slate-800 bg-slate-900/60 px-2 py-1 text-[11px]">
            <p>ΔP: {diff?.probability == null ? "UNAVAILABLE" : diff.probability}</p>
            <p>ΔE: {diff?.exposure == null ? "UNAVAILABLE" : diff.exposure}</p>
            <p>ΔS: {diff?.severity == null ? "UNAVAILABLE" : diff.severity}</p>
          </div>
        </div>
      </section>
      <section>
        <h3 className="text-[11px] font-semibold uppercase text-slate-500">Digital twin causal chain</h3>
        <ol className="space-y-1 text-[11px]">
          {chain.map((link) => (
            <li key={link.name} className="rounded border border-slate-800 px-2 py-1">
              <p className="font-medium">{link.name}</p>
              <p className="text-slate-400">
                {link.status}
                {link.status === "NOT MODELED" ? " — relationship not represented by this run." : ""}
              </p>
              <p className="text-[10px] text-slate-500">{link.note}</p>
            </li>
          ))}
        </ol>
      </section>
      <section>
        <h3 className="text-[11px] font-semibold uppercase text-slate-500">Impact (Phase 7.3)</h3>
        <p className="text-[11px]">
          Hospitals affected: {impact?.categories?.hospitals?.affected == null ? "UNAVAILABLE" : impact.categories.hospitals.affected}
        </p>
        <p className="text-[11px]">
          Roads: {impact?.categories?.roads?.status || "UNAVAILABLE"}
        </p>
        <p className="text-[11px]">
          {impact?.categories?.population?.affected == null
            ? "POPULATION EXPOSURE: UNAVAILABLE"
            : `POPULATION EXPOSURE: ${impact.categories.population.affected}`}
        </p>
      </section>
    </aside>
  );
}
