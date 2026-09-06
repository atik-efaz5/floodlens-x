function TypeChip({ type }) {
  const label = type || "UNKNOWN";
  const tone =
    label === "FORECAST"
      ? "border-sky-500/40 text-sky-200"
      : label === "OBSERVATION"
        ? "border-emerald-500/40 text-emerald-200"
        : label === "SCENARIO"
          ? "border-violet-500/40 text-violet-200"
          : "border-amber-500/40 text-amber-200";
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase ${tone}`}>{label}</span>
  );
}

export default function HistoryCompareBar({
  predictions,
  compare,
  selectedPredictionId,
  onSelectPrediction,
  onGenerateReport,
  report,
  generating,
}) {
  const rows = predictions || [];
  return (
    <section className="space-y-2 border-t border-slate-800 px-4 py-2 text-xs text-slate-200" aria-label="Prediction and comparison">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          Predictions / scenarios / simulations
        </h2>
        <button
          type="button"
          className="rounded border border-slate-600 px-2 py-1 text-[11px] text-sky-200"
          onClick={onGenerateReport}
          disabled={generating}
        >
          {generating ? "Generating…" : "Generate historical report"}
        </button>
      </div>
      <p className="text-[10px] text-slate-500">
        Semantic type is retained. A scenario is never labeled FORECAST. A raster is not automatically a forecast.
      </p>
      <div className="flex flex-wrap gap-2">
        {rows.map((row) => (
          <button
            key={row.prediction_id}
            type="button"
            onClick={() => onSelectPrediction?.(row)}
            className={`min-w-[10rem] rounded-lg border px-2 py-2 text-left ${
              selectedPredictionId === row.prediction_id
                ? "border-sky-400 bg-sky-500/20"
                : "border-slate-800 bg-slate-900/70"
            }`}
          >
            <TypeChip type={row.semantic_type} />
            <p className="mt-1 text-[11px] font-semibold">{row.model || row.prediction_id}</p>
            <p className="text-[10px] text-slate-500">status {row.status || "UNAVAILABLE"}</p>
            <p className="text-[10px] text-slate-500">target {row.target_definition || "UNAVAILABLE"}</p>
          </button>
        ))}
        {!rows.length && <p className="text-amber-200">No prediction candidates listed.</p>}
      </div>
      <div className="rounded border border-slate-800 bg-slate-900/60 p-2" aria-live="polite">
        <p className="font-semibold">
          COMPARISON: {compare?.comparison || "UNAVAILABLE"}
        </p>
        <p className="text-[11px] text-amber-200">{compare?.reason}</p>
        <p className="text-[10px] text-slate-500">
          Depth: {compare?.depth_comparison || "UNAVAILABLE"}. Timing: {compare?.timing_error?.status || "UNAVAILABLE"}.
        </p>
        {compare?.metrics && (
          <p className="text-[11px]">
            IoU {compare.metrics.iou ?? "UNAVAILABLE"} · Dice {compare.metrics.dice ?? "UNAVAILABLE"} ·
            precision {compare.metrics.precision ?? "UNAVAILABLE"} · recall {compare.metrics.recall ?? "UNAVAILABLE"}
          </p>
        )}
        <p className="text-[10px] text-slate-500">
          Difference classes (when comparable): TP predicted+observed flood · FP false alarm · FN missed flood · TN dry.
          Color is not the only encoding.
        </p>
      </div>
      {report && (
        <p className="text-[11px] text-slate-400">
          Report {report.id} generated at {report.generated_at}. Forecast accuracy omitted unless comparison is COMPARABLE.
        </p>
      )}
    </section>
  );
}
