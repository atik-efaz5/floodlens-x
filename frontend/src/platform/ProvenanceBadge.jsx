const STATUS_STYLES = {
  REAL: "bg-emerald-500/20 text-emerald-100 border-emerald-400/40",
  SIMULATED: "bg-amber-500/20 text-amber-100 border-amber-400/40",
  DEMO: "bg-amber-500/20 text-amber-100 border-amber-400/40",
  STALE: "bg-orange-500/20 text-orange-100 border-orange-400/40",
  UNAVAILABLE: "bg-slate-500/20 text-slate-200 border-slate-400/40",
  PARTIAL: "bg-sky-500/20 text-sky-100 border-sky-400/40",
  EXPERIMENTAL: "bg-violet-500/20 text-violet-100 border-violet-400/40",
};

const LEGACY = {
  live: "REAL",
  recent: "REAL",
  stale: "STALE",
  unavailable: "UNAVAILABLE",
  demo: "DEMO",
  snapshot: "REAL",
  static: "REAL",
};

export function normalizeDataStatus(value) {
  if (!value) {
    return "UNAVAILABLE";
  }
  const raw = String(value);
  if (STATUS_STYLES[raw]) {
    return raw;
  }
  return LEGACY[raw.toLowerCase()] || "UNAVAILABLE";
}

export default function ProvenanceBadge({ status, freshness, fallbackUsed, className = "" }) {
  const label = normalizeDataStatus(status);
  const style = STATUS_STYLES[label] || STATUS_STYLES.UNAVAILABLE;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${style} ${className}`}
    >
      {label}
      {freshness ? <span className="font-normal opacity-80">· {String(freshness)}</span> : null}
      {fallbackUsed ? <span className="font-normal opacity-80">· fallback</span> : null}
    </span>
  );
}
