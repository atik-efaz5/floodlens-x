import { useEffect, useState } from "react";

import { fetchDataSources } from "./api";
import ProvenanceBadge from "./ProvenanceBadge";

export default function DataSourcesPanel({ cityId, visible }) {
  const [catalog, setCatalog] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!visible || !cityId) {
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    fetchDataSources(cityId)
      .then((data) => {
        if (!cancelled) {
          setCatalog(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setCatalog(null);
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
  }, [cityId, visible]);

  if (!visible) {
    return null;
  }

  return (
    <section className="glass-panel mt-3 rounded-lg px-4 py-3 text-sm text-slate-200">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Data sources
      </h2>
      {loading && <p className="text-xs text-slate-400">Loading catalog…</p>}
      {error && <p className="text-xs text-amber-200">Catalog unavailable: {error}</p>}
      {!loading && !error && !catalog?.sources?.length && (
        <p className="text-xs text-slate-400">No data sources registered for this city.</p>
      )}
      <ul className="space-y-2">
        {(catalog?.sources || []).map((source) => (
          <li key={source.id} className="flex items-start justify-between gap-2">
            <div>
              <p className="text-xs font-medium">{source.title}</p>
              <p className="text-[11px] text-slate-400">{source.provider}</p>
              {source.note ? <p className="text-[11px] text-slate-500">{source.note}</p> : null}
            </div>
            <ProvenanceBadge
              status={source.data_status}
              freshness={source.freshness}
              fallbackUsed={source.fallback_used}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
