import DataHealthPanel from "./DataHealthPanel";
import DataSourcesPanel from "./DataSourcesPanel";
import JobsListPanel from "./JobsListPanel";
import ModelStatusPanel from "./ModelStatusPanel";

export default function AdminCenter({ cityId, visible, onSelectJob }) {
  if (!visible) {
    return null;
  }
  return (
    <section className="space-y-3 px-4 py-3" aria-label="Admin operations">
      <h2 className="text-lg font-semibold text-slate-100">Admin</h2>
      <p className="text-xs text-amber-200">
        Demo IdP only. SYSTEM HEALTH is process liveness. DATA AVAILABILITY is catalog status and is
        often UNAVAILABLE even when the API is healthy.
      </p>
      <DataHealthPanel cityId={cityId} visible />
      <DataSourcesPanel cityId={cityId} visible />
      <ModelStatusPanel visible />
      <JobsListPanel visible onSelectJob={onSelectJob} />
      <section className="glass-panel rounded-lg px-4 py-3 text-xs text-slate-300">
        <h3 className="mb-1 font-semibold uppercase tracking-wide text-slate-400">Audit</h3>
        <p>Assistant tool calls are stored in the in-memory platform store audit log.</p>
        <p>Reports and shares are immutable snapshots. Revoke does not rewrite history.</p>
        <p>Spatial AI: NOT_VALIDATED. Spatial API: UNAVAILABLE. Model training: NOT AUTHORIZED.</p>
      </section>
    </section>
  );
}
