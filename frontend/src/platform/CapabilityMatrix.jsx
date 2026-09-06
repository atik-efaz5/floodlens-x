import { CAPABILITIES } from "./capabilities";
import ProvenanceBadge from "./ProvenanceBadge";

export default function CapabilityMatrix({ visible }) {
  if (!visible) {
    return null;
  }
  return (
    <section className="glass-panel mt-3 rounded-lg px-4 py-3 text-xs text-slate-200" data-testid="capability-matrix">
      <h2 className="mb-2 font-semibold uppercase tracking-wide text-slate-400">Capability matrix</h2>
      <p className="mb-2 text-[11px] text-slate-500">
        Status is product truth, not a completeness cosmetic. Zeros are not used for unknown values.
      </p>
      <ul className="space-y-2">
        {CAPABILITIES.map((row) => (
          <li key={row.id} className="border-b border-slate-800/80 pb-2 last:border-0">
            <div className="flex items-start justify-between gap-2">
              <p className="font-medium text-slate-100">{row.label}</p>
              <ProvenanceBadge status={row.status} />
            </div>
            <p className="mt-1 text-[11px] text-slate-400">{row.note}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
