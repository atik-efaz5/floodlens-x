import { useState } from "react";

import ProvenanceBadge from "../platform/ProvenanceBadge";

function Field({ label, value }) {
  const missing = value == null || value === "" || value === undefined;
  return (
    <p className="text-[11px] text-slate-300">
      <span className="text-slate-500">{label}: </span>
      {missing ? "UNAVAILABLE" : String(value)}
    </p>
  );
}

function Section({ id, title, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="border-b border-slate-800 py-2 last:border-0">
      <h3>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={`explore-section-${id}`}
          id={`explore-heading-${id}`}
          onClick={() => setOpen((value) => !value)}
          className="flex w-full items-center justify-between text-left text-xs font-semibold uppercase tracking-wide text-slate-400"
        >
          {title}
          <span aria-hidden>{open ? "−" : "+"}</span>
        </button>
      </h3>
      {open && (
        <div id={`explore-section-${id}`} role="region" aria-labelledby={`explore-heading-${id}`} className="mt-2 space-y-1">
          {children}
        </div>
      )}
    </section>
  );
}

export default function SelectedAreaPanel({
  cityName,
  cityId,
  selection,
  risk,
  flood,
  forecast,
  river,
  infrastructure,
  nearby,
  dataStatus,
  onOpenForecast,
  onOpenRiver,
  onOpenImpact,
}) {
  const lat = selection?.latitude;
  const lon = selection?.longitude;
  return (
    <aside className="space-y-2 text-slate-200" aria-label="Selected-area analysis">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Selected area</h2>
      <Section id="overview" title="Overview">
        <Field label="Region" value={cityName || cityId} />
        <Field label="Region ID" value={selection?.region_id || cityId} />
        <Field label="Latitude" value={Number.isFinite(lat) ? lat.toFixed(5) : null} />
        <Field label="Longitude" value={Number.isFinite(lon) ? lon.toFixed(5) : null} />
        <p className="text-[10px] text-slate-500">
          Coordinate clicks expose lat/lon only. Administrative names are not invented.
        </p>
      </Section>
      <Section id="risk" title="Risk">
        <Field label="Category" value={risk?.category} />
        <Field label="Probability" value={risk?.probability} />
        <Field label="Exposure" value={risk?.exposure} />
        <Field label="Severity" value={risk?.severity} />
        <p className="text-[10px] text-slate-500">Risk = P × E × S. Not confidence.</p>
        <ProvenanceBadge status={risk?.provenance?.data_status} freshness={risk?.provenance?.freshness} />
      </Section>
      <Section id="flood" title="Flood" defaultOpen>
        <Field label="Flood status" value={flood?.status} />
        <Field label="Probability" value={flood?.probability} />
        <Field label="Forecast horizon" value={flood?.horizon} />
        <Field
          label="Depth"
          value={
            flood?.depth_m == null || flood?.depth_m === 0
              ? null
              : `${Number(flood.depth_m).toFixed(3)} m`
          }
        />
        <Field label="Exposure" value={flood?.exposure} />
        <Field label="Source" value={flood?.source} />
        <Field label="Timestamp" value={flood?.timestamp} />
        <p className="text-[10px] text-slate-500">Unavailable values are labeled UNAVAILABLE, never shown as zero.</p>
      </Section>
      <Section id="forecast" title="Forecast">
        <Field label="Product" value={forecast?.model_kind || forecast?.disclaimer} />
        <ProvenanceBadge status={forecast?.data_status || "DEMO"} />
        <p className="text-[10px] text-slate-500">
          Heuristic hours are DEMO. Spatial AI 6–72h maps are UNAVAILABLE.
        </p>
        {onOpenForecast && (
          <button type="button" onClick={onOpenForecast} className="text-[11px] text-sky-300 underline">
            Open Forecast workspace
          </button>
        )}
      </Section>
      <Section id="rivers" title="Rivers" defaultOpen={Boolean(river)}>
        {river ? (
          <>
            <Field label="River" value={river.name || river.river_id || river.id} />
            <Field label="Segment" value={river.segment_id || river.segment?.id} />
            <Field
              label="Upstream"
              value={
                (river.upstream || []).length
                  ? (river.upstream || []).map((row) => row.id).join(", ")
                  : "none listed"
              }
            />
            <Field
              label="Downstream"
              value={
                (river.downstream || []).length
                  ? (river.downstream || []).map((row) => row.id).join(", ")
                  : "none listed"
              }
            />
            <Field label="Source" value={river.provenance?.provider || "openstreetmap"} />
            <Field label="Geometry" value={river.segment?.geometry ? "LineString" : null} />
            <Field label="Water level" value={null} />
            <Field label="Discharge" value={null} />
            <ProvenanceBadge status={river.data_status || river.provenance?.data_status} />
            {onOpenImpact && (
              <button type="button" onClick={onOpenImpact} className="text-[11px] text-sky-300 underline">
                Open Impact workspace
              </button>
            )}
          </>
        ) : (
          <p className="text-[11px] text-slate-400">No river segment selected.</p>
        )}
      </Section>
      <Section id="infrastructure" title="Infrastructure" defaultOpen={Boolean(infrastructure || nearby?.length)}>
        {infrastructure ? (
          <>
            <Field label="Name" value={infrastructure.name} />
            <Field label="Type" value={infrastructure.type} />
            <Field
              label="Coordinates"
              value={
                Number.isFinite(infrastructure.latitude) && Number.isFinite(infrastructure.longitude)
                  ? `${infrastructure.latitude.toFixed(5)}, ${infrastructure.longitude.toFixed(5)}`
                  : null
              }
            />
            <Field label="Source" value={infrastructure.source} />
            <Field label="Timestamp" value={infrastructure.timestamp} />
            <Field
              label="Flood impact"
              value={infrastructure.impact_computed ? infrastructure.flood_impact : "NOT_COMPUTED"}
            />
            <Field
              label="Accessibility"
              value={infrastructure.accessibility_computed ? infrastructure.accessibility : "NOT_COMPUTED"}
            />
            {infrastructure.type === "road" && (
              <p className="text-[11px] text-slate-300">
                ROAD FLOOD IMPACT: {infrastructure.impact_computed ? infrastructure.flood_impact : "NOT_COMPUTED"}
              </p>
            )}
            <ProvenanceBadge status={infrastructure.data_status} />
          </>
        ) : (
          <p className="text-[11px] text-slate-400">No infrastructure asset selected.</p>
        )}
        <p className="mt-2 text-[10px] uppercase tracking-wide text-slate-500">Nearby (bbox)</p>
        {(nearby || []).length === 0 ? (
          <p className="text-[11px] text-slate-400">No nearby features in the click bbox.</p>
        ) : (
          <ul className="max-h-28 space-y-1 overflow-y-auto text-[11px]">
            {(nearby || []).slice(0, 12).map((item) => (
              <li key={item.properties?.id || item.properties?.name}>
                {item.properties?.name || "Unnamed"} · {item.properties?.asset_type || "feature"}
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section id="data" title="Data">
        <Field label="Source" value={dataStatus?.source} />
        <Field label="Dataset" value={dataStatus?.dataset} />
        <ProvenanceBadge status={dataStatus?.status} freshness={dataStatus?.freshness} fallbackUsed={dataStatus?.fallbackUsed} />
        <p className="text-[10px] text-slate-500">{dataStatus?.note || "LIVE is never claimed for simulated products."}</p>
      </Section>
    </aside>
  );
}
