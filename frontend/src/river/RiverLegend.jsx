export default function RiverLegend() {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900/60 p-2 text-[10px] text-slate-300" aria-label="River map legend">
      <h3 className="mb-1 font-semibold uppercase tracking-wide text-slate-400">River legend</h3>
      <p className="mb-1 text-slate-500">Topology colors are not risk colors.</p>
      <ul className="space-y-1">
        <li><span className="mr-1 inline-block h-2 w-4 rounded-sm bg-amber-400" aria-hidden /> Selected segment</li>
        <li><span className="mr-1 inline-block h-2 w-4 rounded-sm bg-teal-400" aria-hidden /> Upstream neighbor</li>
        <li><span className="mr-1 inline-block h-2 w-4 rounded-sm bg-violet-400" aria-hidden /> Downstream neighbor</li>
        <li><span className="mr-1 inline-block h-2 w-4 rounded-sm bg-indigo-400" aria-hidden /> Reachable downstream (network)</li>
        <li><span className="mr-1 inline-block h-2 w-4 rounded-sm bg-sky-500" aria-hidden /> Other river geometry</li>
      </ul>
    </section>
  );
}
