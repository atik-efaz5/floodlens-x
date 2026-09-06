export default function ImpactLegend() {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900/60 p-2 text-[10px] text-slate-300" aria-label="Impact map legend">
      <h3 className="mb-1 font-semibold uppercase tracking-wide text-slate-400">Impact legend</h3>
      <p className="mb-1 text-slate-500">Type colors are not flood-risk categories. Exposure uses outline only.</p>
      <ul className="space-y-1">
        <li><span className="mr-1 inline-block h-2 w-2 rounded-full bg-red-500" aria-hidden /> Hospital</li>
        <li><span className="mr-1 inline-block h-2 w-2 rounded-full bg-yellow-400" aria-hidden /> School</li>
        <li><span className="mr-1 inline-block h-2 w-2 rounded-full bg-sky-400" aria-hidden /> Bridge</li>
        <li><span className="mr-1 inline-block h-2 w-2 rounded-full bg-green-500" aria-hidden /> Shelter</li>
        <li><span className="mr-1 inline-block h-2 w-4 rounded-sm bg-slate-500" aria-hidden /> Road geometry</li>
        <li><span className="mr-1 inline-block h-2 w-2 rounded-full border-2 border-rose-400" aria-hidden /> Exposed (computed)</li>
        <li><span className="mr-1 inline-block h-2 w-2 rounded-full border border-slate-400" aria-hidden /> Not exposed / unknown</li>
      </ul>
    </section>
  );
}
