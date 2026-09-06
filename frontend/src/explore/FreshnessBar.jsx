import ProvenanceBadge, { normalizeDataStatus } from "../platform/ProvenanceBadge";

function relativeAge(iso) {
  if (!iso) {
    return null;
  }
  const then = Date.parse(iso);
  if (!Number.isFinite(then)) {
    return null;
  }
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes} min ago`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 48) {
    return `${hours} h ago`;
  }
  return `${Math.round(hours / 24)} d ago`;
}

export default function FreshnessBar({ provenance, label }) {
  const status = normalizeDataStatus(provenance?.data_status || provenance?.status);
  const age = relativeAge(provenance?.retrieved_at || provenance?.valid_at || provenance?.timestamp);
  const neverLive = status === "DEMO" || status === "SIMULATED" || provenance?.simulated;
  return (
    <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-300" aria-live="polite">
      <span className="text-slate-500">{label || "Data freshness"}</span>
      <ProvenanceBadge status={status} freshness={provenance?.freshness} fallbackUsed={provenance?.fallback_used} />
      {age && (status === "REAL" || status === "STALE") && (
        <span>
          UPDATED {age}
        </span>
      )}
      {neverLive && <span className="text-amber-200">Not LIVE</span>}
      {status === "UNAVAILABLE" && <span>No qualifying live source.</span>}
    </div>
  );
}
