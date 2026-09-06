export default function ScenarioPresets({ onSelectPreset }) {
  const presets = [
    {
      name: "Normal Monsoon",
      icon: "🌧️",
      rainfall_rate: 5.0e-6,
      duration: 3600,
      nx: 80,
      ny: 80,
    },
    {
      name: "Severe Flash Flood",
      icon: "⚡",
      rainfall_rate: 1.5e-5,
      duration: 1800,
      nx: 120,
      ny: 120,
    },
    {
      name: "Extreme Cloudburst",
      icon: "🌪️",
      rainfall_rate: 3.0e-5,
      duration: 900,
      nx: 150,
      ny: 150,
    },
  ];

  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
        Quick Presets
      </h2>
      <div className="space-y-2">
        {presets.map((preset) => (
          <button
            key={preset.name}
            onClick={() =>
              onSelectPreset({
                rainfall_rate: preset.rainfall_rate,
                duration_seconds: preset.duration,
                nx: preset.nx,
                ny: preset.ny,
              })
            }
            className="glass-panel group w-full rounded-lg px-4 py-3 text-left transition hover:border-flood-400/60 hover:bg-slate-800/50"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="flex items-center gap-2 text-sm font-medium text-white">
                  <span className="text-lg">{preset.icon}</span>
                  {preset.name}
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  {(preset.rainfall_rate * 3600 * 1000).toFixed(1)} mm/hr •{" "}
                  {preset.duration}s • {preset.nx}x{preset.ny}
                </p>
              </div>
              <div className="text-lg opacity-0 transition group-hover:opacity-100">
                →
              </div>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
