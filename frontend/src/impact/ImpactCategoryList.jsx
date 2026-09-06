const CATEGORIES = [
  { id: "hospital", label: "Hospitals" },
  { id: "school", label: "Schools" },
  { id: "bridge", label: "Bridges" },
  { id: "road", label: "Roads" },
  { id: "shelter", label: "Shelters" },
  { id: "critical", label: "Critical" },
];

export default function ImpactCategoryList({ value, onChange, summary }) {
  return (
    <section aria-label="Impact categories">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Categories</h3>
      <div className="flex flex-wrap gap-1">
        <button
          type="button"
          aria-pressed={!value}
          onClick={() => onChange("")}
          className={`rounded-full px-2 py-1 text-[11px] ${!value ? "bg-sky-700 text-white" : "bg-slate-800 text-slate-300"}`}
        >
          All
        </button>
        {CATEGORIES.map((row) => (
          <button
            key={row.id}
            type="button"
            aria-pressed={value === row.id}
            onClick={() => onChange(row.id)}
            className={`rounded-full px-2 py-1 text-[11px] ${
              value === row.id ? "bg-sky-700 text-white" : "bg-slate-800 text-slate-300"
            }`}
          >
            {row.label}
          </button>
        ))}
      </div>
      {summary?.categories && (
        <ul className="mt-2 space-y-1 text-[11px] text-slate-400">
          {Object.entries(summary.categories).map(([key, row]) => (
            <li key={key}>
              {key}: {row.status}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
