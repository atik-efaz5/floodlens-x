import { COMPARISON_LAYERS, COMPARISON_MODES } from "../comparison/state";

export default function ComparisonPanel({
  compareMode,
  onToggle,
  cityId,
  cityName,
  scenarioOptions,
  scenarioAId,
  scenarioBId,
  onScenarioAChange,
  onScenarioBChange,
  comparisonMode,
  onComparisonModeChange,
  comparisonLayer,
  onComparisonLayerChange,
  comparisonResult,
  comparisonError,
  scenarioA,
  scenarioB,
  jobCompare,
}) {
  const summaries = comparisonResult?.comparison?.scenario_summaries;
  const stats = comparisonResult?.comparison?.summary_statistics;
  const extent = comparisonResult?.comparison?.extent_categories;

  return (
    <section className="border-b border-slate-800 px-5 py-4">
      <label className="flex items-center justify-between text-sm">
        <span className="font-medium text-slate-200">Compare Mode</span>
        <input
          type="checkbox"
          checked={compareMode}
          onChange={(event) => onToggle(event.target.checked)}
          className="accent-flood-500"
        />
      </label>

      {compareMode && (
        <div className="mt-4 space-y-3">
          <p className="text-xs text-slate-400">
            City: <span className="font-semibold text-slate-100">{cityName || cityId}</span>
          </p>

          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs text-slate-400">
              Scenario A
              <select
                value={scenarioAId}
                onChange={(event) => onScenarioAChange(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-2 py-2 text-xs text-slate-100"
              >
                <option value="">Select</option>
                {scenarioOptions.map((option) => (
                  <option key={`a-${option.scenario_id}`} value={option.scenario_id}>
                    {option.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-slate-400">
              Scenario B
              <select
                value={scenarioBId}
                onChange={(event) => onScenarioBChange(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-2 py-2 text-xs text-slate-100"
              >
                <option value="">Select</option>
                {scenarioOptions.map((option) => (
                  <option key={`b-${option.scenario_id}`} value={option.scenario_id}>
                    {option.name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {COMPARISON_MODES.map((mode) => (
              <button
                key={mode.id}
                type="button"
                onClick={() => onComparisonModeChange(mode.id)}
                className={`rounded-lg px-2 py-2 text-xs font-medium ${
                  comparisonMode === mode.id
                    ? "bg-flood-700 text-white"
                    : "border border-slate-700 bg-slate-800 text-slate-200"
                }`}
              >
                {mode.label}
              </button>
            ))}
          </div>

          <div className="space-y-1">
            {COMPARISON_LAYERS.map((layer) => (
              <label
                key={layer.id}
                className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-800/50 px-3 py-2 text-xs"
              >
                <span>{layer.label}</span>
                <input
                  type="radio"
                  name="comparison-layer"
                  checked={comparisonLayer === layer.id}
                  onChange={() => onComparisonLayerChange(layer.id)}
                  className="accent-flood-500"
                />
              </label>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="rounded-lg border border-slate-800 bg-slate-800/60 p-3">
              <p className="font-semibold text-slate-300">Scenario A</p>
              <p className="mt-1 text-slate-400">{scenarioA?.label || scenarioAId || "Not loaded"}</p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-800/60 p-3">
              <p className="font-semibold text-slate-300">Scenario B</p>
              <p className="mt-1 text-slate-400">{scenarioB?.label || scenarioBId || "Not loaded"}</p>
            </div>
          </div>

          {summaries && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100">
              <p>
                Δ Max Depth: {summaries.maximum_depth_difference_m >= 0 ? "+" : ""}
                {summaries.maximum_depth_difference_m.toFixed(3)} m
              </p>
              <p className="mt-1">
                Δ Flooded Area: {summaries.flooded_area_difference_km2 >= 0 ? "+" : ""}
                {summaries.flooded_area_difference_km2.toFixed(3)} km²
              </p>
              <p className="mt-1">
                Δ Peak Velocity: {summaries.peak_velocity_difference_m_s >= 0 ? "+" : ""}
                {summaries.peak_velocity_difference_m_s.toFixed(3)} m/s
              </p>
            </div>
          )}

          {stats && (
            <div className="rounded-lg border border-slate-700 bg-slate-800/70 p-3 text-xs text-slate-200">
              <p>Mean |Δ|: {stats.mean_absolute_difference.toFixed(4)}</p>
              <p className="mt-1">RMSE: {stats.rmse.toFixed(4)}</p>
              <p className="mt-1">
                Max |Δ|: {stats.maximum_absolute_difference.toFixed(4)}
              </p>
            </div>
          )}

          {extent && (
            <div className="rounded-lg border border-slate-700 bg-slate-800/70 p-3 text-xs text-slate-200">
              <p>Both: {extent.flooded_in_both}</p>
              <p>Only A: {extent.flooded_only_in_a}</p>
              <p>Only B: {extent.flooded_only_in_b}</p>
              <p>Neither: {extent.flooded_in_neither}</p>
            </div>
          )}

          {comparisonError && (
            <p className="text-xs text-red-300">{comparisonError}</p>
          )}

          {jobCompare && (
            <div className="rounded-lg border border-slate-700 bg-slate-800/70 p-3 text-xs text-slate-200">
              <p className="mb-2 font-medium">Physics job compare</p>
              <div className="grid grid-cols-2 gap-2">
                <input
                  value={jobCompare.jobA}
                  onChange={(event) => jobCompare.onJobAChange(event.target.value)}
                  placeholder="Baseline job id"
                  className="rounded border border-slate-600 bg-slate-900 px-2 py-1"
                />
                <input
                  value={jobCompare.jobB}
                  onChange={(event) => jobCompare.onJobBChange(event.target.value)}
                  placeholder="Scenario job id"
                  className="rounded border border-slate-600 bg-slate-900 px-2 py-1"
                />
              </div>
              <button
                type="button"
                onClick={jobCompare.onCompare}
                className="mt-2 rounded bg-sky-600 px-2 py-1 text-[10px] uppercase text-white"
              >
                Compare jobs
              </button>
              {jobCompare.loading && <p className="mt-1 text-slate-400">Comparing…</p>}
              {jobCompare.error && <p className="mt-1 text-amber-200">{jobCompare.error}</p>}
              {jobCompare.result?.difference && (
                <p className="mt-1">
                  Δ depth {Number(jobCompare.result.difference.max_depth_m).toFixed(3)} m · Δ area{" "}
                  {Number(jobCompare.result.difference.flooded_area_km2).toFixed(4)} km² · population null
                </p>
              )}
              <p className="mt-2 text-[10px] text-amber-200">
                River-level scenario parameter recorded; physical river-boundary coupling is not enabled.
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
