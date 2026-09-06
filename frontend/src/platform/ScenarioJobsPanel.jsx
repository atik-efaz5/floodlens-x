import { useState } from "react";

import { postScenarioJob } from "./api";

const MULTIPLIERS = [
  { label: "Baseline ×1.0", value: 1.0 },
  { label: "Rainfall +20%", value: 1.2 },
  { label: "Rainfall +30%", value: 1.3 },
  { label: "Rainfall +50%", value: 1.5 },
];

export default function ScenarioJobsPanel({ cityId, visible, onJobQueued }) {
  const [error, setError] = useState(null);
  const [lastJob, setLastJob] = useState(null);
  const [pending, setPending] = useState(false);

  if (!visible) {
    return null;
  }

  const run = async (multiplier) => {
    setPending(true);
    setError(null);
    try {
      const job = await postScenarioJob(cityId, { rainfall_multiplier: multiplier });
      setLastJob(job);
      onJobQueued?.(job);
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  };

  return (
    <section className="glass-panel mt-3 rounded-lg px-4 py-3 text-xs text-slate-200">
      <h2 className="mb-2 font-semibold uppercase tracking-wide text-slate-400">
        Physics rainfall scenarios
      </h2>
      <p className="mb-2 text-slate-400">
        Forcing: forecast mm → m/s via SIMPLE_RUNOFF_BASELINE, then × multiplier. Requires
        Emergency/Researcher/Admin.
      </p>
      <div className="flex flex-wrap gap-1">
        {MULTIPLIERS.map((item) => (
          <button
            key={item.value}
            type="button"
            disabled={pending}
            onClick={() => run(item.value)}
            className="rounded bg-slate-800 px-2 py-1 text-[10px] uppercase text-white disabled:opacity-50"
          >
            {item.label}
          </button>
        ))}
      </div>
      <p className="mt-2 text-amber-200">
        River-level scenario parameter recorded; physical river-boundary coupling is not enabled.
      </p>
      {lastJob && (
        <p className="mt-1 text-slate-400">
          Queued {lastJob.job_id || lastJob.id} · {lastJob.status}
        </p>
      )}
      {error && <p className="mt-1 text-amber-200">{error}</p>}
    </section>
  );
}
