import { useState } from "react";

const RAINFALL = [
  { label: "Baseline ×1.0", value: 1.0 },
  { label: "+10%", value: 1.1 },
  { label: "+20%", value: 1.2 },
  { label: "+30%", value: 1.3 },
  { label: "+50%", value: 1.5 },
  { label: "+100%", value: 2.0 },
];

function Field({ label, value }) {
  return (
    <p className="text-[11px] text-slate-300">
      <span className="text-slate-500">{label}: </span>
      {value == null || value === "" ? "UNAVAILABLE" : String(value)}
    </p>
  );
}

export default function ScenarioControls({
  cityId,
  cityName,
  baseline,
  capabilities,
  history,
  rainfallMultiplier,
  onRainfallMultiplier,
  riverDeltaM,
  onRiverDeltaM,
  scenarioName,
  onScenarioName,
  selectedBaselineId,
  onSelectBaseline,
  pending,
  error,
  onRun,
  onOpenHistory,
}) {
  const [announce, setAnnounce] = useState("");
  const unsupported = (capabilities || []).filter((row) => row.status === "NOT_IMPLEMENTED");
  const rainfallCap = (capabilities || []).find((row) => row.id === "rainfall_multiplier");
  const riverCap = (capabilities || []).find((row) => row.id === "river_level_delta_m");

  const submit = (event) => {
    event.preventDefault();
    const percent = Math.round((Number(rainfallMultiplier) - 1) * 100);
    const name = scenarioName || (percent === 0 ? "Baseline ×1.0" : `Rainfall ${percent > 0 ? "+" : ""}${percent}%`);
    setAnnounce(`Queuing scenario ${name} for ${cityName || cityId}.`);
    onRun?.({
      name,
      rainfall_multiplier: Number(rainfallMultiplier),
      river_level_delta_m: Number(riverDeltaM) || 0,
      baseline_id: selectedBaselineId || undefined,
    });
  };

  return (
    <form className="space-y-3 text-slate-200" aria-label="Scenario controls" onSubmit={submit}>
      <div className="sr-only" aria-live="polite">
        {announce}
        {error ? `Scenario error: ${error}` : ""}
      </div>
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Scenario controls</h2>
      <Field label="Region" value={cityName || cityId} />
      <Field label="Baseline job" value={baseline?.job_id || selectedBaselineId} />
      <Field label="Baseline forcing" value={baseline?.forcing?.status} />
      <Field label="Model" value={baseline?.model} />
      <p className="text-[10px] text-slate-500">{rainfallCap?.note}</p>

      <label className="block text-[11px] text-slate-400">
        Scenario name
        <input
          value={scenarioName}
          onChange={(event) => onScenarioName(event.target.value)}
          className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        />
      </label>

      <fieldset>
        <legend className="text-[11px] font-medium text-slate-300">Rainfall multiplier</legend>
        <div className="mt-1 flex flex-wrap gap-1">
          {RAINFALL.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={Number(rainfallMultiplier) === item.value}
              onClick={() => {
                onRainfallMultiplier(item.value);
                onScenarioName(item.value === 1 ? "Baseline ×1.0" : `Rainfall ${item.label}`);
              }}
              className={`rounded px-2 py-1 text-[10px] uppercase ${
                Number(rainfallMultiplier) === item.value
                  ? "bg-flood-500 text-white"
                  : "bg-slate-800 text-slate-200"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <label className="mt-2 block text-[11px] text-slate-400">
          Explicit multiplier
          <input
            type="number"
            min="0"
            max="10"
            step="0.05"
            value={rainfallMultiplier}
            onChange={(event) => onRainfallMultiplier(event.target.value)}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          />
        </label>
        <p className="mt-1 font-mono text-[10px] text-slate-500">rainfall_multiplier = {rainfallMultiplier}</p>
      </fieldset>

      <fieldset>
        <legend className="text-[11px] font-medium text-slate-300">River level delta</legend>
        <label className="mt-1 block text-[11px] text-slate-400">
          river_level_delta_m
          <input
            type="number"
            step="0.1"
            value={riverDeltaM}
            onChange={(event) => onRiverDeltaM(event.target.value)}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          />
        </label>
        <p className="mt-1 text-[10px] text-amber-200" role="note">
          STORED SCENARIO PARAMETER. NOT CURRENTLY APPLIED TO SWE SOLVER. Solver coupling: NOT APPLIED.
        </p>
        <p className="text-[10px] text-slate-500">{riverCap?.note}</p>
      </fieldset>

      <label className="block text-[11px] text-slate-400">
        Reopen saved baseline
        <select
          value={selectedBaselineId || ""}
          onChange={(event) => onSelectBaseline(event.target.value)}
          className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        >
          <option value="">Current / new baseline</option>
          {(history || []).map((row) => (
            <option key={row.job_id || row.id} value={row.job_id || row.id}>
              {row.name || row.kind} · {row.status} · {row.created_at || "UNAVAILABLE"}
            </option>
          ))}
        </select>
      </label>

      <button
        type="submit"
        disabled={pending}
        className="w-full rounded bg-flood-700 px-3 py-2 text-xs font-semibold uppercase text-white disabled:opacity-50"
      >
        {pending ? "Queuing…" : "Run scenario"}
      </button>
      {error && (
        <p className="text-[11px] text-red-300" role="alert">
          SIMULATION FAILED: {error}
        </p>
      )}

      <section>
        <h3 className="text-[11px] font-semibold uppercase text-slate-500">Unsupported controls</h3>
        <ul className="mt-1 space-y-1 text-[10px] text-slate-400">
          {unsupported.map((row) => (
            <li key={row.id}>
              {row.label}: {row.status}. {row.note}
            </li>
          ))}
        </ul>
      </section>
      <button
        type="button"
        className="text-left text-[11px] text-sky-300 underline"
        onClick={onOpenHistory}
      >
        Recent scenarios
      </button>
    </form>
  );
}
