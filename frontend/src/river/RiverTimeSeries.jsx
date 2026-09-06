import ProvenanceBadge from "../platform/ProvenanceBadge";

function Chart({ series, field, label, units }) {
  const points = (series || []).filter((row) => row.available && row[field] != null);
  if (points.length < 2) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-2 text-[11px] text-slate-400">
        <p className="font-medium text-slate-300">{label}</p>
        <p>No {label.toLowerCase()} series. Reason: fewer than two observed points.</p>
      </div>
    );
  }
  const values = points.map((row) => Number(row[field]));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 280;
  const height = 56;
  const d = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-2">
      <p className="text-[11px] font-medium text-slate-200">
        {label} ({units})
      </p>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="mt-1 w-full text-sky-300"
        role="img"
        aria-label={`${label} time series, ${points.length} points`}
      >
        <path d={d} fill="none" stroke="currentColor" strokeWidth="2" />
      </svg>
    </div>
  );
}

export default function RiverTimeSeries({ observations }) {
  const series = observations?.observations || [];
  return (
    <section className="border-t border-slate-800 bg-slate-950/95 px-4 py-2 text-slate-100" aria-label="River time series">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h2 className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          Observations / provenance
        </h2>
        <ProvenanceBadge status={observations?.provenance?.data_status || "UNAVAILABLE"} />
      </div>
      <p className="mb-2 text-[10px] text-slate-500">
        Forecast series UNAVAILABLE. DEMO topology is never mixed into REAL gauge values.
      </p>
      <div className="grid gap-2 md:grid-cols-2">
        <Chart series={series} field="water_level_m" label="Water level" units="m" />
        <Chart series={series} field="discharge_m3s" label="Discharge" units="m³/s" />
      </div>
    </section>
  );
}
