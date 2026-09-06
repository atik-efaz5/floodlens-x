import { useEffect, useState } from "react";

import { fetchJobs } from "./api";
import PanelState from "./PanelState";
import ProvenanceBadge from "./ProvenanceBadge";

function durationLabel(job) {
  if (!job?.started_at || !job?.completed_at) {
    if (job?.status === "running" || job?.status === "queued") {
      return "in progress";
    }
    return "UNAVAILABLE";
  }
  const ms = Date.parse(job.completed_at) - Date.parse(job.started_at);
  if (!Number.isFinite(ms) || ms < 0) {
    return "UNAVAILABLE";
  }
  return `${(ms / 1000).toFixed(1)}s`;
}

const STATUS_LABEL = {
  queued: "QUEUED",
  running: "RUNNING",
  completed: "COMPLETED",
  failed: "FAILED",
};

export default function JobsListPanel({ visible, onSelectJob }) {
  const [jobs, setJobs] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!visible) {
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    fetchJobs()
      .then((data) => {
        if (!cancelled) {
          setJobs(data.jobs || []);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
          setJobs(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [visible]);

  if (!visible) {
    return null;
  }

  let state = "SUCCESS";
  if (loading) state = "LOADING";
  else if (error) state = "ERROR";
  else if (!(jobs || []).length) state = "EMPTY";

  return (
    <PanelState
      title="Recent simulations"
      state={state}
      message={error || (state === "EMPTY" ? "No jobs in this session." : undefined)}
    >
      <ul className="max-h-56 space-y-2 overflow-y-auto">
        {(jobs || []).slice().reverse().slice(0, 12).map((job) => {
          const id = job.job_id || job.id;
          const label = STATUS_LABEL[job.status] || String(job.status || "").toUpperCase();
          return (
            <li key={id}>
              <button
                type="button"
                onClick={() => onSelectJob?.(job)}
                className="w-full rounded border border-slate-800 bg-slate-900/60 px-2 py-2 text-left text-[11px] hover:border-slate-600"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-slate-100">{id}</span>
                  <ProvenanceBadge status={job.status === "failed" ? "UNAVAILABLE" : "SIMULATED"} />
                </div>
                <p className="mt-1 text-slate-300">
                  {label} · {job.city_id} · {job.kind}
                </p>
                <p className="text-slate-500">
                  started {job.started_at || "UNAVAILABLE"} · duration {durationLabel(job)} · model{" "}
                  {job.model_version || "UNAVAILABLE"}
                </p>
              </button>
            </li>
          );
        })}
      </ul>
    </PanelState>
  );
}
