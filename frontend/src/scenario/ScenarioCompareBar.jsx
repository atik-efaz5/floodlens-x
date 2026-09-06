import ProvenanceBadge from "../platform/ProvenanceBadge";

function fmt(value) {
  if (value == null || value === "") return "UNAVAILABLE";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "UNAVAILABLE";
  return String(value);
}

function statusLabel(row) {
  if (!row) return "UNAVAILABLE";
  if (row.data_status) return row.data_status;
  if (row.status === "failed") return "FAILED";
  if (row.available === false) return "NOT_COMPUTED";
  if (row.available) return "SIMULATED";
  return row.status || "UNAVAILABLE";
}

export default function ScenarioCompareBar({
  workspace,
  baselineJob,
  scenarioJob,
  difference,
  impact,
  times,
  selectedTime,
  onSelectTime,
  onGenerateReport,
  report,
}) {
  const rows = workspace?.compare?.comparisons || [];
  const extra = (workspace?.history || []).slice(0, 2);
  const table = [
    { label: "BASELINE", row: rows[0] || baselineJob },
    { label: "SCENARIO A", row: rows[1] || scenarioJob },
    { label: "SCENARIO B", row: extra[0] },
    { label: "EXTREME", row: extra.find((item) => Number(item?.rainfall_multiplier) >= 2) || extra[1] },
  ];
  const job = scenarioJob || baselineJob;
  const result = job?.result || {};
  return (
    <section className="border-t border-slate-800 bg-slate-950/95 px-4 py-2 text-slate-100" aria-label="Scenario comparison">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          Comparison / impact / provenance
        </h2>
        <ProvenanceBadge status={workspace?.provenance?.data_status || result.data_status || "SIMULATED"} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-[10px] text-slate-300">
          <caption className="sr-only">Baseline versus scenario comparison</caption>
          <thead>
            <tr className="text-slate-500">
              <th scope="col">Scenario</th>
              <th scope="col">Forcing change</th>
              <th scope="col">Flood extent</th>
              <th scope="col">Max depth</th>
              <th scope="col">Risk</th>
              <th scope="col">Infrastructure exposure</th>
              <th scope="col">Population exposure</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {table.map((item) => (
              <tr key={item.label} className="border-t border-slate-800">
                <th scope="row">{item.label}</th>
                <td>{fmt(item.row?.rainfall_multiplier ?? item.row?.result?.rainfall_multiplier)}</td>
                <td>{fmt(item.row?.flooded_area_km2 ?? item.row?.result?.flooded_area_km2)}</td>
                <td>{fmt(item.row?.max_depth_m ?? item.row?.result?.max_depth_m)}</td>
                <td>{fmt(item.row?.risk?.score)}</td>
                <td>{impact?.categories?.hospitals?.affected == null ? "UNAVAILABLE" : impact.categories.hospitals.affected}</td>
                <td>UNAVAILABLE</td>
                <td>{statusLabel(item.row)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-[10px] text-slate-400">
        Difference map: {difference?.available ? `absolute SCENARIO − BASELINE · artifact ${difference.artifact_id}` : difference?.reason || "UNAVAILABLE"}
        {difference?.available
          ? ` · newly flooded cells ${difference.newly_flooded_cells} · reduced ${difference.reduced_flood_cells}`
          : ""}
      </p>
      {times?.length ? (
        <div className="mt-1 flex flex-wrap items-center gap-1 text-[10px]">
          <span className="text-slate-500">Simulation times (seconds, not meteorological hours):</span>
          {times.map((time, index) => (
            <button
              key={time}
              type="button"
              aria-pressed={selectedTime === time}
              onClick={() => onSelectTime(time)}
              className={`rounded px-2 py-0.5 ${
                selectedTime === time ? "bg-sky-700 text-white" : "bg-slate-800 text-slate-200"
              }`}
            >
              T{index} = {time}s
            </button>
          ))}
        </div>
      ) : (
        <p className="mt-1 text-[10px] text-slate-500">Timeline: no additional simulated frames. 6/12/24/48/72h states are not manufactured.</p>
      )}
      <p className="mt-1 text-[10px] text-slate-400">
        Input {result.dem_source || "scenario-service"} · forcing multiplier {fmt(result.rainfall_multiplier)} ·
        model {job?.model_version || result.model_version || "UNAVAILABLE"} · job {job?.id || "UNAVAILABLE"} ·
        artifact {result.artifact_id || "UNAVAILABLE"} · {workspace?.generated_at || job?.completed_at || "UNAVAILABLE"}
      </p>
      <p className="text-[10px] text-amber-200">
        Solver coupling: NOT APPLIED. river_level_applied_to_solver = false. Failures are shown, not clipped.
      </p>
      <button type="button" className="mt-1 text-[11px] text-sky-300 underline" onClick={onGenerateReport}>
        Open report
      </button>
      {report && (
        <p className="text-[10px] text-slate-400">
          Report {report.id} · Analysis generated at {report.generated_at}. Job {report.scenario_id || report.body?.scenario?.job_id || "UNAVAILABLE"}.
        </p>
      )}
    </section>
  );
}
