import { useEffect, useState } from "react";

import { fetchModels } from "./api";

export default function ModelStatusPanel({ visible }) {
  const [catalog, setCatalog] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!visible) {
      return undefined;
    }
    let cancelled = false;
    fetchModels()
      .then((data) => {
        if (!cancelled) {
          setCatalog(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [visible]);

  if (!visible) {
    return null;
  }
  return (
    <section className="glass-panel mt-3 rounded-lg px-4 py-3 text-xs text-slate-200">
      <h2 className="mb-2 font-semibold uppercase tracking-wide text-slate-400">Models</h2>
      {error && <p className="text-amber-200">Model catalog unavailable: {error}</p>}
      {!error && !catalog && <p className="text-slate-400">Loading models…</p>}
      {(catalog?.models || []).map((model) => (
        <p key={model.id}>
          {model.title}: {model.display_status || model.status}
          {model.accuracy_claim == null ? " · no accuracy claim" : ""}
          {model.label_kind ? ` · ${model.label_kind}` : ""}
        </p>
      ))}
      <div className="mt-3 rounded border border-slate-800 bg-slate-900/60 p-2">
        <p className="font-semibold text-slate-100">Spatial AI</p>
        <p>NOT_VALIDATED</p>
        <p>Spatial API: UNAVAILABLE</p>
        <p className="text-slate-400">
          Validated AOI GBDT is an AOI probability task, not an “AI flood map.”
        </p>
      </div>
      <p className="mt-2 text-[10px] text-slate-500">
        AI catalog shows VALIDATED only after a held-out real-data evaluation. Until then: NOT_TRAINED.
        AOI GBDT labels may be MODELLED (GloFAS Q), not flood maps.         Spatial AI:
        TRAINED — NOT VALIDATED
        until held-out independent events, baselines, and uncertainty coverage are all documented.
        Phase 6 Gate 2 is not passed; the spatial API stays UNAVAILABLE (not production, not “AI Powered”).
        It does not inherit AOI GBDT VALIDATED. Physics is a short SWE burst, not 24h inundation.
        COMPARISON NOT YET COMPARABLE. No accuracy % without metric, dataset, split, and horizon.
      </p>
    </section>
  );
}
