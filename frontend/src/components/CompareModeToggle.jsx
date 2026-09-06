export default function CompareModeToggle({
  compareMode,
  onToggle,
  activeSlot,
  onSlotChange,
  comparisonStats,
  scenarioA,
  scenarioB,
}) {
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
          <div className="grid grid-cols-2 gap-2">
            {["A", "B"].map((slot) => (
              <button
                key={slot}
                type="button"
                onClick={() => onSlotChange(slot)}
                className={`rounded-lg px-3 py-2 text-sm font-medium ${
                  activeSlot === slot
                    ? "bg-flood-700 text-white"
                    : "border border-slate-700 bg-slate-800 text-slate-200"
                }`}
              >
                Scenario {slot}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="rounded-lg border border-slate-800 bg-slate-800/60 p-3">
              <p className="font-semibold text-slate-300">Scenario A</p>
              <p className="mt-1 text-slate-400">
                {scenarioA?.label || "Not loaded"}
              </p>
              <p className="mt-2 text-white">
                {scenarioA?.runResult
                  ? `${scenarioA.runResult.max_depth_m.toFixed(3)} m`
                  : "—"}
              </p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-800/60 p-3">
              <p className="font-semibold text-slate-300">Scenario B</p>
              <p className="mt-1 text-slate-400">
                {scenarioB?.label || "Not loaded"}
              </p>
              <p className="mt-2 text-white">
                {scenarioB?.runResult
                  ? `${scenarioB.runResult.max_depth_m.toFixed(3)} m`
                  : "—"}
              </p>
            </div>
          </div>

          {comparisonStats && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
              <p>
                Δ Max Depth: {comparisonStats.deltaMaxDepth >= 0 ? "+" : ""}
                {comparisonStats.deltaMaxDepth.toFixed(3)} m
              </p>
              <p className="mt-1">
                Δ Flooded Area: {comparisonStats.deltaFloodedArea >= 0 ? "+" : ""}
                {comparisonStats.deltaFloodedArea.toFixed(3)} km²
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
