import { useEffect, useState } from "react";

import { fetchExperiments, fetchResearchCompare } from "./api";
import PanelState from "./PanelState";
import ProvenanceBadge from "./ProvenanceBadge";

export default function ResearchDiagnostics({ visible }) {
  const [compare, setCompare] = useState(null);
  const [experiments, setExperiments] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!visible) {
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    Promise.all([fetchResearchCompare(), fetchExperiments()])
      .then(([cmp, exp]) => {
        if (!cancelled) {
          setCompare(cmp);
          setExperiments(exp);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
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

  return (
    <PanelState title="Research diagnostics" state={state} message={error}>
      <p className="text-[11px] text-slate-400">
        Spatial AI remains NOT_VALIDATED. Target B is PARTIALLY FEASIBLE. Model training is not authorized here.
      </p>
      {compare && (
        <div className="mt-2 space-y-1 text-xs">
          <p>
            Spatial AI: {compare.ai_spatial?.status || "NOT_VALIDATED"} · API UNAVAILABLE
          </p>
          <p>
            Comparison: {compare.comparison_status || compare.note || compare.status || "see payload"}{" "}
            <ProvenanceBadge status={compare.comparable_to_physics ? "PARTIAL" : "UNAVAILABLE"} />
          </p>
          {compare.physics?.footnote || compare.note ? (
            <p className="text-slate-500">{compare.physics?.footnote || compare.note}</p>
          ) : null}
        </div>
      )}
      <p className="mt-2 text-[11px] text-slate-500">
        Experiments: {(experiments?.experiments || experiments?.items || []).length || 0} recorded
      </p>
    </PanelState>
  );
}
