import ProvenanceBadge from "./ProvenanceBadge";

const LABELS = {
  LOADING: "Loading",
  SUCCESS: "Ready",
  EMPTY: "Empty",
  ERROR: "Error",
  UNAVAILABLE: "Unavailable",
  STALE: "Stale",
  DEMO: "Demo",
  SIMULATED: "Simulated",
  EXPERIMENTAL: "Experimental",
  PARTIAL: "Partial",
};

export default function PanelState({
  state = "SUCCESS",
  title,
  children,
  message,
  as: Tag = "section",
}) {
  const key = String(state || "SUCCESS").toUpperCase();
  const showBody = key === "SUCCESS" || key === "PARTIAL" || key === "DEMO" || key === "SIMULATED" || key === "STALE" || key === "EXPERIMENTAL";
  return (
    <Tag
      className="glass-panel rounded-lg px-4 py-3 text-sm text-slate-200"
      data-panel-state={key}
      aria-busy={key === "LOADING"}
      aria-live={key === "ERROR" || key === "UNAVAILABLE" ? "polite" : undefined}
    >
      {title ? (
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">{title}</h2>
      ) : null}
      {key === "LOADING" && <p className="animate-pulse text-xs text-slate-400">{message || "Loading…"}</p>}
      {key === "EMPTY" && <p className="text-xs text-slate-400">{message || "No records."}</p>}
      {key === "ERROR" && <p className="text-xs text-amber-200">{message || "Request failed."}</p>}
      {key === "UNAVAILABLE" && (
        <p className="text-xs text-slate-300">
          <ProvenanceBadge status="UNAVAILABLE" /> {message || "This product is UNAVAILABLE. No value is shown."}
        </p>
      )}
      {showBody ? children : null}
      {key !== "SUCCESS" && key !== "LOADING" && LABELS[key] ? (
        <p className="sr-only">{LABELS[key]}</p>
      ) : null}
    </Tag>
  );
}
