function Field({ label, value }) {
  return (
    <p className="text-[11px] text-slate-300">
      <span className="text-slate-500">{label}: </span>
      {value == null || value === "" ? "UNAVAILABLE" : String(value)}
    </p>
  );
}

export default function ModelPerformanceCenter({ payload, selectedId, onSelect }) {
  const models = payload?.models || [];
  const selected =
    models.find((row) => row.id === selectedId) || payload?.selected || models[0] || {};
  const headline = selected.headline || {};
  const splits = selected.split_counts || selected.splits || {};
  return (
    <section className="space-y-3 text-xs text-slate-200" aria-label="Model performance center">
      <h1 className="text-lg font-semibold">Model performance</h1>
      <p className="rounded border border-amber-900/60 bg-amber-950/40 px-2 py-1 text-[11px]">
        SPATIAL AI STATUS: {payload?.spatial_ai?.status || "NOT_VALIDATED"}. Spatial API:{" "}
        {payload?.spatial_ai?.spatial_api || "UNAVAILABLE"}. No generic “94% accurate” claim.
      </p>
      <ul className="space-y-1" role="listbox" aria-label="Model registry">
        {models.map((row) => (
          <li key={row.id}>
            <button
              type="button"
              role="option"
              aria-selected={row.id === selected.id}
              className={`w-full rounded border px-2 py-1 text-left ${
                row.id === selected.id ? "border-sky-400 bg-sky-500/20" : "border-slate-800 bg-slate-900/70"
              }`}
              onClick={() => onSelect?.(row)}
            >
              <p className="font-semibold">{row.title || row.id}</p>
              <p className="text-[10px] text-slate-400">
                {row.kind} · {row.display_status || row.scientific_status || row.status}
              </p>
            </button>
          </li>
        ))}
      </ul>
      <div className="rounded border border-slate-800 bg-slate-900/60 p-2">
        <Field label="model_id" value={selected.model_id || selected.id} />
        <Field label="version" value={selected.version} />
        <Field label="task" value={selected.task || headline.task} />
        <Field label="dataset" value={selected.training_dataset || headline.dataset} />
        <Field label="dataset version" value={headline.dataset_version || selected.training_dataset} />
        <Field label="train split" value={typeof splits.train === "object" ? JSON.stringify(splits.train) : splits.train} />
        <Field label="validation split" value={typeof splits.val === "object" ? JSON.stringify(splits.val) : splits.val} />
        <Field label="test split" value={typeof splits.test === "object" ? JSON.stringify(splits.test) : splits.test} />
        <Field label="forecast horizon" value={headline.horizon} />
        <Field label="target definition" value={headline.target || selected.task} />
        <Field label="IoU" value={headline.iou} />
        <Field label="AUPRC" value={headline.auprc} />
        <Field label="Brier" value={headline.brier} />
        <Field label="F1" value={headline.f1} />
        <Field label="n_test_samples" value={headline.n_test_samples} />
        <Field label="test events" value={headline.test_events} />
        <Field label="uncertainty" value={selected.uncertainty?.status} />
        <Field label="calibrated" value={selected.uncertainty?.calibrated === true ? "calibrated" : selected.uncertainty?.available ? "not calibrated" : "unavailable"} />
        <Field label="accuracy_claim" value={selected.accuracy_claim} />
        {headline.statistical_power_limited && (
          <p className="mt-2 rounded border border-amber-700 px-2 py-1 text-[11px] text-amber-200">
            STATISTICAL POWER LIMITED
          </p>
        )}
        {(selected.limitations || []).map((line) => (
          <p key={line} className="text-[10px] text-slate-500">
            {line}
          </p>
        ))}
        {selected.kind === "AI" && (
          <p className="mt-2 text-[11px] text-amber-200">
            AOI GBDT is a validated AOI probability task, not a spatial flood map model.
          </p>
        )}
        {selected.kind === "AI_SPATIAL" && (
          <p className="mt-2 text-[11px] text-amber-200">
            STATUS: NOT_VALIDATED. No spatial-AI forecast metrics are shown.
          </p>
        )}
      </div>
    </section>
  );
}
