const FILTERS = [
  { id: "all", label: "All" },
  { id: "hospitals", label: "Hospitals" },
  { id: "schools", label: "Schools" },
  { id: "bridges", label: "Bridges" },
  { id: "roads", label: "Roads" },
  { id: "critical", label: "Critical" },
  { id: "shelters", label: "Shelters" },
];

export default function InfraFilterBar({ value, onChange }) {
  return (
    <div className="flex flex-wrap gap-1" role="toolbar" aria-label="Infrastructure filters">
      {FILTERS.map((item) => (
        <button
          key={item.id}
          type="button"
          aria-pressed={value === item.id}
          onClick={() => onChange(item.id)}
          className={`rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-wide ${
            value === item.id ? "bg-sky-600 text-white" : "bg-slate-800 text-slate-300 hover:bg-slate-700"
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
