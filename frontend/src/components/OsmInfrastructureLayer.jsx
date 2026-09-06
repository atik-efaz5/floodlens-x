import { useEffect, useMemo, useState } from "react";
import { CircleMarker, Popup, Polyline, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";

import { fetchInfrastructure } from "../platform/api";

const TYPE_COLORS = {
  hospital: "#ef4444",
  school: "#eab308",
  clinic: "#f97316",
  shelter: "#22c55e",
  emergency: "#a855f7",
  bridge: "#38bdf8",
  road: "#64748b",
};

function bboxFromMap(map) {
  const bounds = map.getBounds();
  return [
    bounds.getWest(),
    bounds.getSouth(),
    bounds.getEast(),
    bounds.getNorth(),
  ].join(",");
}

function clusterPoints(features, zoom) {
  if (zoom >= 13) {
    return features.map((feature) => ({ kind: "point", feature }));
  }
  const buckets = new Map();
  const step = zoom >= 11 ? 0.01 : 0.03;
  features.forEach((feature) => {
    if (feature.geometry?.type !== "Point") {
      return;
    }
    const [lon, lat] = feature.geometry.coordinates;
    const key = `${Math.round(lat / step)}_${Math.round(lon / step)}`;
    if (!buckets.has(key)) {
      buckets.set(key, []);
    }
    buckets.get(key).push(feature);
  });
  const clustered = [];
  buckets.forEach((group) => {
    if (group.length === 1) {
      clustered.push({ kind: "point", feature: group[0] });
      return;
    }
    const lat =
      group.reduce((sum, item) => sum + item.geometry.coordinates[1], 0) / group.length;
    const lon =
      group.reduce((sum, item) => sum + item.geometry.coordinates[0], 0) / group.length;
    clustered.push({ kind: "cluster", count: group.length, lat, lon });
  });
  return clustered;
}

function inspectPayload(feature, floodSummary, impact) {
  const coords = feature.geometry?.coordinates || [];
  const lon = feature.geometry?.type === "Point" ? coords[0] : coords[0]?.[0];
  const lat = feature.geometry?.type === "Point" ? coords[1] : coords[0]?.[1];
  const kind = feature.properties?.asset_type || "feature";
  const computed = Boolean(impact && impact.impact_status && impact.impact_status !== "NOT_COMPUTED");
  return {
    name: feature.properties?.name || "Unnamed",
    type: kind,
    latitude: lat,
    longitude: lon,
    source: feature.properties?.source || "openstreetmap",
    timestamp: feature.properties?.updated_at || feature.properties?.timestamp || impact?.timestamp || null,
    data_status: feature.properties?.data_status,
    regional_max_depth_m: floodSummary?.max_depth_m ?? null,
    depth_m: impact?.expected_depth_m ?? null,
    depth_note: impact?.expected_depth_m == null ? "EXPECTED DEPTH: UNAVAILABLE" : "point sample",
    flood_impact: impact?.impact_status || "NOT_COMPUTED",
    impact_computed: computed,
    accessibility: "NOT_COMPUTED",
    accessibility_computed: false,
    computation: impact?.computation,
  };
}

export default function OsmInfrastructureLayer({
  cityId,
  typeFilter = "",
  enabledTypes,
  onStatus,
  onFeatureInspect,
  floodSummary,
  impactById,
}) {
  const map = useMap();
  const [features, setFeatures] = useState([]);
  const [zoom, setZoom] = useState(map.getZoom());

  useMapEvents({
    zoomend: () => setZoom(map.getZoom()),
    moveend: () => setZoom(map.getZoom()),
  });

  useEffect(() => {
    if (!cityId) {
      return undefined;
    }
    if (Array.isArray(enabledTypes) && enabledTypes.length === 0) {
      setFeatures([]);
      onStatus?.({ status: "idle" });
      return undefined;
    }
    let cancelled = false;
    const handle = setTimeout(() => {
      onStatus?.({ status: "loading" });
      const apiType =
        typeFilter || (enabledTypes && enabledTypes.length === 1 ? enabledTypes[0] : "");
      fetchInfrastructure(cityId, { bbox: bboxFromMap(map), type: apiType, limit: 400 })
        .then((data) => {
          if (cancelled) {
            return;
          }
          const next = data.features || [];
          setFeatures(next);
          onStatus?.({ status: next.length ? "ok" : "empty", count: next.length });
        })
        .catch((err) => {
          if (cancelled) {
            return;
          }
          setFeatures([]);
          onStatus?.({ status: "error", error: err.message });
        });
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [cityId, typeFilter, enabledTypes, map, zoom]);

  const visible = useMemo(() => {
    if (!enabledTypes || enabledTypes.length === 0) {
      return typeFilter ? features.filter((row) => row.properties?.asset_type === typeFilter) : features;
    }
    return features.filter((row) => enabledTypes.includes(row.properties?.asset_type));
  }, [features, enabledTypes, typeFilter]);

  const markers = useMemo(
    () => clusterPoints(visible.filter((f) => f.geometry?.type === "Point"), zoom),
    [visible, zoom]
  );
  const lines = useMemo(
    () => visible.filter((f) => f.geometry?.type === "LineString").slice(0, 80),
    [visible]
  );

  return (
    <>
      {lines.map((feature) => (
        <Polyline
          key={feature.properties?.id || JSON.stringify(feature.geometry.coordinates[0])}
          positions={feature.geometry.coordinates.map(([lng, lat]) => [lat, lng])}
          eventHandlers={{
            click: (event) => {
              L.DomEvent.stopPropagation(event);
              onFeatureInspect?.(inspectPayload(feature, floodSummary, impactById?.[feature.properties?.id]));
            },
          }}
          pathOptions={{ color: TYPE_COLORS.road, weight: 3, opacity: 0.75 }}
        >
          <Popup>
            <div className="text-sm">
              <p className="font-semibold">{feature.properties?.name || "Unnamed road"}</p>
              <p>Road geometry (not a flood prediction)</p>
              <p className="text-xs">
                {impactById?.[feature.properties?.id]?.impact_status
                  ? `ROAD FLOOD IMPACT: ${impactById[feature.properties.id].impact_status}`
                  : "ROAD FLOOD IMPACT: NOT_COMPUTED"}
              </p>
              <p className="text-xs">{feature.properties?.data_status}</p>
            </div>
          </Popup>
        </Polyline>
      ))}
      {markers.map((item, index) => {
        if (item.kind === "cluster") {
          return (
            <CircleMarker
              key={`cluster-${index}`}
              center={[item.lat, item.lon]}
              radius={10}
              pathOptions={{ color: "#fff", fillColor: "#0ea5e9", fillOpacity: 0.85, weight: 1 }}
            >
              <Popup>{item.count} OSM features</Popup>
            </CircleMarker>
          );
        }
        const [lng, lat] = item.feature.geometry.coordinates;
        const kind = item.feature.properties?.asset_type || "hospital";
        const impact = impactById?.[item.feature.properties?.id];
        const exposed = impact?.impact_status === "EXPOSED" || impact?.impact_status === "AFFECTED";
        return (
          <CircleMarker
            key={item.feature.properties?.id || `${lat}-${lng}`}
            center={[lat, lng]}
            radius={7}
            eventHandlers={{
              click: (event) => {
                L.DomEvent.stopPropagation(event);
                onFeatureInspect?.(inspectPayload(item.feature, floodSummary, impact));
              },
            }}
            pathOptions={{
              color: exposed ? "#fb7185" : "#ffffff",
              weight: exposed ? 3 : 1.5,
              fillColor: TYPE_COLORS[kind] || "#f97316",
              fillOpacity: 0.95,
            }}
          >
            <Popup>
              <div className="text-sm">
                <p className="font-semibold">{item.feature.properties?.name || "Unnamed"}</p>
                <p>{kind}</p>
                <p className="text-xs">
                  {lat.toFixed(5)}, {lng.toFixed(5)}
                </p>
                <p className="text-xs">{item.feature.properties?.data_status}</p>
                <p className="text-xs">Flood exposure: {impact?.impact_status || "NOT_COMPUTED"}</p>
                <p className="text-xs">
                  EXPECTED DEPTH:{" "}
                  {impact?.expected_depth_m == null ? "UNAVAILABLE" : `${impact.expected_depth_m} m`}
                </p>
                <p className="text-xs">
                  Per-feature depth:{" "}
                  {impact?.expected_depth_m == null ? "NOT_COMPUTED" : `${impact.expected_depth_m} m`}
                </p>
                <p className="text-xs">
                  Regional maximum depth (not substituted as expected depth):{" "}
                  {floodSummary?.max_depth_m == null
                    ? "UNAVAILABLE"
                    : `${Number(floodSummary.max_depth_m).toFixed(3)} m`}
                </p>
                <p className="text-xs">Accessibility NOT_COMPUTED</p>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </>
  );
}
