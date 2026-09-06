import { useEffect, useRef, useState } from "react";

import { fetchJob } from "./api";

export default function JobProgressPanel({ jobId, visible, onComplete }) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const doneRef = useRef(null);

  useEffect(() => {
    if (!visible || !jobId) {
      return undefined;
    }
    doneRef.current = null;
    let cancelled = false;
    const poll = () => {
      fetchJob(jobId)
        .then((data) => {
          if (cancelled) {
            return;
          }
          setJob(data);
          setError(null);
          if (
            (data.status === "completed" || data.status === "failed") &&
            doneRef.current !== data.status
          ) {
            doneRef.current = data.status;
            onComplete?.(data);
          }
        })
        .catch((err) => {
          if (!cancelled) {
            setError(err.message);
          }
        });
    };
    poll();
    const handle = setInterval(poll, 1500);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, [jobId, visible, onComplete]);

  if (!visible) {
    return null;
  }
  if (!jobId) {
    return (
      <section className="glass-panel mt-3 rounded-lg px-4 py-3 text-xs text-slate-400">
        No physics job queued. Run a forecast or scenario to see progress.
      </section>
    );
  }
  if (error) {
    return (
      <section className="glass-panel mt-3 rounded-lg px-4 py-3 text-xs text-amber-200">
        Job status unavailable: {error}
      </section>
    );
  }
  const status = String(job?.status || "queued").toUpperCase();
  const failed = status === "FAILED";
  return (
    <section className="glass-panel mt-3 rounded-lg px-4 py-3 text-xs text-slate-200" aria-live="polite">
      <h3 className="mb-1 font-semibold uppercase tracking-wide text-slate-400">Job progress</h3>
      <p>
        {job?.job_id || jobId} · {job?.kind || "…"} · {status}
        {failed ? " · SIMULATION FAILED" : ""}
      </p>
      <p className="mt-1 text-slate-400">
        Lifecycle {job?.lifecycle || "CREATE"}. Solver percent UNAVAILABLE (backend reports queued/running/completed/failed only).
      </p>
      <p className="mt-1 text-slate-400">
        validation {job?.validation_status || "—"}
        {job?.error ? ` · ${job.error}` : ""}
      </p>
    </section>
  );
}
