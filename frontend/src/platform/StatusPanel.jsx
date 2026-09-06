import ProvenanceBadge from "./ProvenanceBadge";

const CATEGORY_CLASS = {
  LOW: "text-emerald-200",
  MODERATE: "text-yellow-200",
  HIGH: "text-orange-200",
  CRITICAL: "text-red-200",
};

export default function StatusPanel({ status, error }) {
  if (error) {
    return (
      <section className="glass-panel rounded-lg px-4 py-3 text-sm text-amber-100" data-panel-state="ERROR">
        Status unavailable: {error}
      </section>
    );
  }
  if (!status) {
    return (
      <section className="glass-panel rounded-lg px-4 py-3 text-sm text-slate-400" data-panel-state="EMPTY">
        Search or select a city to load current status, forecast, and data freshness.
      </section>
    );
  }
  const risk = status.risk || {};
  const forecast = status.forecast || {};
  const provenance = risk.provenance || {};
  const category = risk.category || "—";
  return (
    <section className="glass-panel space-y-2 rounded-lg px-4 py-3 text-sm text-slate-200" data-testid="current-risk">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Current risk</h2>
      <p className={`text-lg font-semibold ${CATEGORY_CLASS[category] || "text-white"}`}>{category}</p>
      <p className="text-xs text-slate-300">
        Risk = Probability × Exposure × Severity. These are not “confidence.”
      </p>
      <dl className="grid grid-cols-3 gap-2 text-center text-xs">
        <div className="rounded border border-slate-800 bg-slate-900/50 p-2">
          <dt className="text-slate-500">Probability</dt>
          <dd className="text-base text-white">{risk.probability == null ? "UNAVAILABLE" : Number(risk.probability).toFixed(2)}</dd>
        </div>
        <div className="rounded border border-slate-800 bg-slate-900/50 p-2">
          <dt className="text-slate-500">Exposure</dt>
          <dd className="text-base text-white">{risk.exposure == null ? "UNAVAILABLE" : Number(risk.exposure).toFixed(2)}</dd>
        </div>
        <div className="rounded border border-slate-800 bg-slate-900/50 p-2">
          <dt className="text-slate-500">Severity</dt>
          <dd className="text-base text-white">{risk.severity == null ? "UNAVAILABLE" : Number(risk.severity).toFixed(2)}</dd>
        </div>
      </dl>
      <p className="text-xs text-slate-400">{risk.formula_id}</p>
      <p className="text-xs text-slate-400">{forecast.disclaimer}</p>
      <p className="text-[11px] text-slate-500">
        source {provenance.source || provenance.provider || "—"} · {provenance.retrieved_at || provenance.valid_at || "—"} ·{" "}
        {provenance.dataset || "risk"}
      </p>
      <ProvenanceBadge
        status={provenance.data_status || (provenance.simulated ? "DEMO" : provenance.freshness)}
        freshness={provenance.freshness}
        fallbackUsed={provenance.fallback_used}
      />
    </section>
  );
}
