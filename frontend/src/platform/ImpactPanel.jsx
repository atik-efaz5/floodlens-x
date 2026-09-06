import { useEffect, useState } from "react";

import { fetchJobs, postImpact } from "./api";
import PanelState from "./PanelState";
import ProvenanceBadge from "./ProvenanceBadge";

export default function ImpactPanel({ cityId, visible, preferredJobId }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState([]);
  const [jobId, setJobId] = useState(preferredJobId || "");

  useEffect(() => {
    if (preferredJobId) {
      setJobId(preferredJobId);
    }
  }, [preferredJobId]);

  useEffect(() => {
    if (!visible) {
      return undefined;
    }
    let cancelled = false;
    fetchJobs()
      .then((data) => {
        if (!cancelled) {
          setJobs(data.jobs || []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setJobs([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [visible]);

  if (!visible) {
    return null;
  }

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await postImpact(cityId, jobId || null);
      setResult(data);
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  let state = "SUCCESS";
  if (loading) state = "LOADING";
  else if (error) state = "ERROR";
  else if (result && result.available === false) state = "UNAVAILABLE";

  const counts = result?.flooded_counts || {};
  const roads = result?.roads || result?.line_impact || {};
  const population = result?.population_exposed ?? result?.population?.population_exposed;

  return (
    <PanelState
      title="Impact"
      state={state}
      message={
        error ||
        result?.reason ||
        (state === "UNAVAILABLE" ? "No physics flood raster is attached. Run a simulation first." : undefined)
      }
    >
      <p className="mb-2 text-[11px] text-slate-400">
        Point / line / polygon impact only after a depth raster exists. Population is never invented.
      </p>
      <label className="mb-2 block text-[11px] text-slate-400">
        Physics job
        <select
          value={jobId}
          onChange={(event) => setJobId(event.target.value)}
          className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
        >
          <option value="">None (will report UNAVAILABLE)</option>
          {jobs
            .filter((job) => job.city_id === cityId && job.status === "completed")
            .map((job) => (
              <option key={job.job_id || job.id} value={job.job_id || job.id}>
                {job.job_id || job.id} · {job.kind}
              </option>
            ))}
        </select>
      </label>
      <button
        type="button"
        onClick={run}
        className="rounded bg-slate-700 px-2 py-1 text-[10px] font-semibold uppercase text-white"
      >
        Assess impact
      </button>
      {result && (
        <div className="mt-3 space-y-1 text-xs">
          <p>
            POPULATION EXPOSURE:{" "}
            {population == null ? "UNAVAILABLE" : population}
          </p>
          <p>
            POINT IMPACT: hospitals {counts.hospital ?? "—"} · schools {counts.school ?? "—"}
          </p>
          <p>
            LINE IMPACT:{" "}
            {roads.computed === false
              ? roads.reason || "NOT_COMPUTED"
              : `roads evaluated ${roads.roads_evaluated ?? "—"}`}
          </p>
          <p>POLYGON IMPACT: {result.polygon_impact?.status || "NOT_COMPUTED unless provided"}</p>
          <p>ACCESSIBILITY: {result.accessibility || "NOT_COMPUTED per feature"}</p>
          <ProvenanceBadge status={result.provenance?.data_status || (result.available === false ? "UNAVAILABLE" : "PARTIAL")} />
        </div>
      )}
    </PanelState>
  );
}
