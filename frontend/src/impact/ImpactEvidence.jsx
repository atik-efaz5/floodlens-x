import ProvenanceBadge from "../platform/ProvenanceBadge";

export default function ImpactEvidence({ summary, selectedAsset }) {
  return (
    <section className="border-t border-slate-800 bg-slate-950/95 px-4 py-2 text-slate-100" aria-label="Impact evidence">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          Evidence / assumptions / provenance
        </h2>
        <ProvenanceBadge status={summary?.provenance?.data_status || "PARTIAL"} />
      </div>
      <p className="text-[10px] text-amber-200">{summary?.safety}</p>
      <ul className="mt-1 list-disc pl-4 text-[10px] text-slate-400">
        {(summary?.assumptions || []).map((row) => (
          <li key={row}>{row}</li>
        ))}
      </ul>
      {selectedAsset && (
        <p className="mt-1 text-[11px] text-slate-300">
          Selected {selectedAsset.name}: impact {selectedAsset.impact_status}. Expected depth{" "}
          {selectedAsset.expected_depth_m == null ? "UNAVAILABLE" : `${selectedAsset.expected_depth_m} m`}. Source{" "}
          {selectedAsset.source}. {selectedAsset.computation}.
        </p>
      )}
    </section>
  );
}
