export default function InspectionCard({ inspection, onClose }) {
  if (!inspection) {
    return null;
  }

  const depth = inspection.depth ?? inspection.depth_m ?? 0;
  const velocity = inspection.velocity ?? inspection.velocity_m_s ?? 0;
  const maximumDepth = inspection.maximum_depth ?? inspection.max_depth_m ?? 0;
  const floodStatus =
    inspection.flood_status ??
    (inspection.is_flooded ? "flooded" : "not_flooded");

  return (
    <div className="pointer-events-auto absolute bottom-28 left-6 z-[1000] w-80 rounded-xl border border-slate-200 bg-white/95 p-4 shadow-xl backdrop-blur">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Modeled Cell Inspection
          </p>
          <p className="text-sm font-medium text-slate-900">
            Row {inspection.row}, Col {inspection.column}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Simulated values for the selected grid cell, not field measurements.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
        >
          ×
        </button>
      </div>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-slate-500">Depth</dt>
          <dd className="font-semibold text-flood-700">{depth.toFixed(3)} m</dd>
        </div>
        <div>
          <dt className="text-slate-500">Velocity</dt>
          <dd className="font-semibold text-slate-900">{velocity.toFixed(3)} m/s</dd>
        </div>
        <div>
          <dt className="text-slate-500">Max Depth</dt>
          <dd className="font-semibold text-slate-900">{maximumDepth.toFixed(3)} m</dd>
        </div>
        <div>
          <dt className="text-slate-500">Flood Status</dt>
          <dd
            className={`font-semibold ${
              floodStatus === "flooded" ? "text-flood-700" : "text-slate-700"
            }`}
          >
            {floodStatus === "flooded" ? "Flooded" : "Not flooded"}
          </dd>
        </div>
      </dl>
      <div className="mt-3 space-y-1 text-xs text-slate-500">
        <p>
          {inspection.latitude.toFixed(5)}°N, {inspection.longitude.toFixed(5)}°E
        </p>
        {inspection.city_id && (
          <p>
            City: {inspection.city_id} · Scenario: {inspection.scenario_id}
          </p>
        )}
        {inspection.time !== undefined && (
          <p>Simulation time: {Number(inspection.time).toFixed(2)} s</p>
        )}
      </div>
    </div>
  );
}
