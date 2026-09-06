import { useEffect, useRef, useState } from "react";
import {
  ImageOverlay,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  Rectangle,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";

import InfrastructureLayers from "./InfrastructureLayers";
import OsmInfrastructureLayer from "./OsmInfrastructureLayer";
import RiverNetworkLayer from "./RiverNetworkLayer";
import LayerLegend from "../platform/LayerLegend";
import { getZoomLabel } from "../constants";

const pinIcon = L.divIcon({
  className: "",
  html: '<div style="width:14px;height:14px;border-radius:9999px;background:#1e88e5;border:2px solid white;box-shadow:0 0 0 2px rgba(30,136,229,0.35)"></div>',
  iconSize: [14, 14],
  iconAnchor: [7, 7],
});

function formatMaybe(value, suffix = "") {
  if (value == null || value === "" || Number(value) === 0) {
    return "UNAVAILABLE";
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return String(value);
  }
  return `${numeric.toFixed(3)}${suffix}`;
}

function MapViewportController({ bounds, center, flyTarget }) {
  const map = useMap();

  useEffect(() => {
    if (!bounds) {
      return;
    }
    const leafletBounds = L.latLngBounds(
      [bounds.south, bounds.west],
      [bounds.north, bounds.east]
    );
    map.fitBounds(leafletBounds, { padding: [24, 24] });
  }, [bounds, map]);

  useEffect(() => {
    if (bounds || !center) {
      return;
    }
    map.setView([center.latitude, center.longitude], map.getZoom(), {
      animate: false,
    });
  }, [bounds, center, map]);

  useEffect(() => {
    if (flyTarget) {
      map.flyTo(
        [flyTarget.latitude, flyTarget.longitude],
        flyTarget.zoom || 13,
        { duration: 0.8 }
      );
    }
  }, [flyTarget, map]);

  return null;
}

function MapCommandController({ fitToken, resetToken, bounds, center, defaultZoom = 11 }) {
  const map = useMap();
  const prevFit = useRef(0);
  const prevReset = useRef(0);

  useEffect(() => {
    if (!fitToken || fitToken === prevFit.current) {
      return;
    }
    prevFit.current = fitToken;
    if (!bounds) {
      return;
    }
    map.fitBounds(
      [
        [bounds.south, bounds.west],
        [bounds.north, bounds.east],
      ],
      { padding: [28, 28] }
    );
  }, [fitToken, bounds, map]);

  useEffect(() => {
    if (!resetToken || resetToken === prevReset.current) {
      return;
    }
    prevReset.current = resetToken;
    if (!center) {
      return;
    }
    map.setView([center.latitude, center.longitude], defaultZoom, { animate: true });
  }, [resetToken, center, defaultZoom, map]);

  return null;
}

function ZoomTracker({ onZoomChange }) {
  const map = useMapEvents({
    zoomend: () => onZoomChange(map.getZoom()),
    load: () => onZoomChange(map.getZoom()),
  });

  useEffect(() => {
    onZoomChange(map.getZoom());
  }, [map, onZoomChange]);

  return null;
}

function ViewportSynchronizer({ viewport, onViewportChange }) {
  const map = useMap();
  const applyingRef = useRef(false);

  useMapEvents({
    moveend: () => {
      if (!onViewportChange || applyingRef.current) {
        return;
      }
      const center = map.getCenter();
      onViewportChange({
        center: [center.lat, center.lng],
        zoom: map.getZoom(),
      });
    },
  });

  useEffect(() => {
    if (!viewport?.center) {
      return;
    }
    const current = map.getCenter();
    const sameCenter =
      Math.abs(current.lat - viewport.center[0]) < 1e-8 &&
      Math.abs(current.lng - viewport.center[1]) < 1e-8;
    const sameZoom = map.getZoom() === viewport.zoom;
    if (sameCenter && sameZoom) {
      return;
    }
    applyingRef.current = true;
    map.setView(viewport.center, viewport.zoom, { animate: false });
    applyingRef.current = false;
  }, [map, viewport]);

  return null;
}

function MapClickHandler({
  inspectEnabled,
  onInspect,
  onCoordinateSelect,
  selectionMode,
  onSelectionPoint,
}) {
  const startRef = useRef(null);
  useMapEvents({
    click: (event) => {
      const lat = event.latlng.lat;
      const lng = event.latlng.lng;
      if (selectionMode === "bbox") {
        if (!startRef.current) {
          startRef.current = { lat, lng };
          onSelectionPoint?.({ start: startRef.current, end: null });
          return;
        }
        onSelectionPoint?.({ start: startRef.current, end: { lat, lng } });
        startRef.current = null;
        return;
      }
      onCoordinateSelect?.(lat, lng);
      if (inspectEnabled) {
        onInspect(lat, lng);
      }
    },
  });
  return null;
}

export default function FloodMap({
  mapCenter,
  metadata,
  studyBounds,
  studyCenter,
  overlayUrl,
  overlayBounds,
  showFloodOverlay,
  forecastOverlayUrl,
  onOsmInspect,
  floodSummary,
  infraLayers,
  cityId,
  inspectionPin,
  searchMarker,
  flyTarget,
  hasSimulation,
  onInspect,
  onZoomChange,
  zoomLevel,
  title,
  viewport,
  onViewportChange,
  showForecastOverlay = true,
  onToggleForecast,
  showRainfall = false,
  onToggleRainfall,
  rainfallStatus = "UNAVAILABLE",
  rainfallSummary = null,
  rainfallOverlayUrl = null,
  terrainOverlayUrl = null,
  evacRoutes = null,
  showTerrain = false,
  onToggleTerrain,
  showRivers = true,
  onToggleRivers,
  onCoordinateSelect,
  typeFilter = "",
  enabledTypes,
  showLayerLegend = true,
  fitToken = 0,
  resetToken = 0,
  selectedRiverId,
  selectedSegmentId,
  topologyHighlights,
  impactById,
  onRiverSelect,
  regionSelected = false,
  onRegionSelect,
  selectionMode = "none",
  selectionRect,
  onSelectionPoint,
  osmFilter,
  onOsmFilter,
}) {
  const viewportBounds = studyBounds || metadata?.bounds;
  const viewportCenter = studyCenter || metadata?.center;
  const [internalOsmFilter, setInternalOsmFilter] = useState("");
  const [osmStatus, setOsmStatus] = useState({ status: "idle" });
  const activeOsmFilter = osmFilter != null ? osmFilter : typeFilter || internalOsmFilter;
  const setActiveOsmFilter = onOsmFilter || setInternalOsmFilter;
  const rectangleBounds = viewportBounds
    ? [
        [viewportBounds.south, viewportBounds.west],
        [viewportBounds.north, viewportBounds.east],
      ]
    : null;
  const drawnBounds =
    selectionRect?.start && selectionRect?.end
      ? [
          [
            Math.min(selectionRect.start.lat, selectionRect.end.lat),
            Math.min(selectionRect.start.lng, selectionRect.end.lng),
          ],
          [
            Math.max(selectionRect.start.lat, selectionRect.end.lat),
            Math.max(selectionRect.start.lng, selectionRect.end.lng),
          ],
        ]
      : null;

  return (
    <div className="relative h-full w-full">
      {title && (
        <div className="pointer-events-none absolute left-4 top-4 z-[900] rounded-full border border-white/20 bg-slate-900/80 px-4 py-2 text-sm text-white backdrop-blur">
          {title}
        </div>
      )}

      <MapContainer
        center={mapCenter}
        zoom={10}
        className="h-full w-full"
        scrollWheelZoom
        aria-label="FloodLens-X interactive map"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <MapViewportController
          bounds={viewportBounds}
          center={viewportCenter}
          flyTarget={flyTarget}
        />
        <MapCommandController
          fitToken={fitToken}
          resetToken={resetToken}
          bounds={viewportBounds}
          center={viewportCenter}
          defaultZoom={metadata?.default_zoom || 11}
        />
        <ZoomTracker onZoomChange={onZoomChange} />
        <ViewportSynchronizer viewport={viewport} onViewportChange={onViewportChange} />
        <MapClickHandler
          inspectEnabled={hasSimulation}
          onInspect={onInspect}
          onCoordinateSelect={onCoordinateSelect}
          selectionMode={selectionMode}
          onSelectionPoint={onSelectionPoint}
        />
        <InfrastructureLayers enabledLayers={infraLayers} cityId={cityId} />
        <RiverNetworkLayer
          cityId={cityId}
          visible={showRivers}
          selectedRiverId={selectedRiverId}
          selectedSegmentId={selectedSegmentId}
          topologyHighlights={topologyHighlights}
          onSelect={onRiverSelect}
        />
        <OsmInfrastructureLayer
          cityId={cityId}
          typeFilter={activeOsmFilter}
          enabledTypes={enabledTypes}
          onStatus={setOsmStatus}
          onFeatureInspect={onOsmInspect}
          floodSummary={floodSummary}
          impactById={impactById}
        />
        {rectangleBounds && (
          <Rectangle
            bounds={rectangleBounds}
            eventHandlers={{
              click: (event) => {
                L.DomEvent.stopPropagation(event);
                onRegionSelect?.({
                  cityId,
                  bounds: viewportBounds,
                  kind: "study-bounds",
                });
              },
              mouseover: (event) => event.target.setStyle({ weight: 3 }),
              mouseout: (event) => event.target.setStyle({ weight: regionSelected ? 3 : 2 }),
            }}
            pathOptions={{
              color: regionSelected ? "#fbbf24" : "#38bdf8",
              weight: regionSelected ? 3 : 2,
              fill: false,
              dashArray: "6 4",
            }}
          />
        )}
        {drawnBounds && (
          <Rectangle
            bounds={drawnBounds}
            pathOptions={{ color: "#f59e0b", weight: 2, fillOpacity: 0.08, dashArray: "2 4" }}
          />
        )}
        {overlayUrl && overlayBounds && showFloodOverlay && (
          <ImageOverlay
            url={overlayUrl}
            bounds={overlayBounds}
            opacity={forecastOverlayUrl ? 0.45 : 0.72}
            className="flood-overlay-pane"
          />
        )}
        {forecastOverlayUrl && overlayBounds && showForecastOverlay && (
          <ImageOverlay
            key={forecastOverlayUrl}
            url={forecastOverlayUrl}
            bounds={overlayBounds}
            opacity={0.7}
            className="flood-overlay-pane"
          />
        )}
        {rainfallOverlayUrl && overlayBounds && showRainfall && (
          <ImageOverlay
            url={rainfallOverlayUrl}
            bounds={overlayBounds}
            opacity={0.45}
            className="flood-overlay-pane"
          />
        )}
        {terrainOverlayUrl && overlayBounds && (
          <ImageOverlay
            url={terrainOverlayUrl}
            bounds={overlayBounds}
            opacity={0.35}
            className="flood-overlay-pane"
          />
        )}
        {(evacRoutes?.features || []).map((route) => {
          const coords = route?.geometry?.coordinates || [];
          if (coords.length < 2) {
            return null;
          }
          return (
            <Polyline
              key={route.id || "demo-evac"}
              positions={coords.map((pair) => [pair[1], pair[0]])}
              pathOptions={{ color: "#f59e0b", weight: 4, dashArray: "6 4", opacity: 0.9 }}
            >
              <Popup>
                <div className="text-sm">
                  <p className="font-semibold">{route.name || "DEMO route"}</p>
                  <p className="text-xs">{route.kind || "DEMO EVACUATION ROUTE"}</p>
                  <p className="text-xs">Not an official evacuation order.</p>
                </div>
              </Popup>
            </Polyline>
          );
        })}
        {searchMarker && (
          <Marker position={[searchMarker.latitude, searchMarker.longitude]} icon={pinIcon}>
            <Popup>
              <div className="text-sm">
                <p className="font-semibold">{searchMarker.display_name}</p>
                <p>
                  {searchMarker.latitude.toFixed(4)}°, {searchMarker.longitude.toFixed(4)}°
                </p>
              </div>
            </Popup>
          </Marker>
        )}
        {inspectionPin && (
          <Marker position={[inspectionPin.latitude, inspectionPin.longitude]} icon={pinIcon}>
            <Popup>
              <div className="text-sm">
                <p className="font-semibold">Inspection Point</p>
                <p>Latitude: {inspectionPin.latitude.toFixed(5)}</p>
                <p>Longitude: {inspectionPin.longitude.toFixed(5)}</p>
                <p>Depth: {formatMaybe(inspectionPin.depth ?? inspectionPin.depth_m, " m")}</p>
                <p>
                  Velocity: {formatMaybe(inspectionPin.velocity ?? inspectionPin.velocity_m_s, " m/s")}
                </p>
              </div>
            </Popup>
          </Marker>
        )}
      </MapContainer>

      {showLayerLegend && (
        <LayerLegend
          cityId={cityId}
          visible
          showForecast={showForecastOverlay && Boolean(forecastOverlayUrl)}
          onToggleForecast={() => onToggleForecast?.()}
          showRainfall={showRainfall}
          onToggleRainfall={() => onToggleRainfall?.()}
          rainfallStatus={rainfallStatus}
          rainfallSummary={rainfallSummary}
          showRivers={showRivers}
          onToggleRivers={() => onToggleRivers?.()}
          showTerrain={showTerrain}
          onToggleTerrain={() => onToggleTerrain?.()}
          osmFilter={activeOsmFilter}
          onOsmFilter={setActiveOsmFilter}
        />
      )}
      <div className="pointer-events-none absolute left-4 bottom-4 z-[900] max-w-xs rounded-lg border border-white/20 bg-slate-900/85 p-2 text-xs text-white backdrop-blur">
        {osmStatus.status === "loading" && <p className="text-slate-300">Loading infrastructure…</p>}
        {osmStatus.status === "error" && (
          <p className="text-amber-200">Could not load OSM: {osmStatus.error}</p>
        )}
        {osmStatus.status === "empty" && (
          <p className="text-slate-400">No OSM features in this view.</p>
        )}
        {osmStatus.status === "ok" && (
          <p className="text-slate-400">{osmStatus.count} features · bbox fetch (capped)</p>
        )}
        {osmStatus.status === "idle" && (
          <p className="text-slate-400">Infrastructure layer idle.</p>
        )}
      </div>
      <div className="pointer-events-none absolute right-4 top-4 z-[900] rounded-full border border-white/20 bg-slate-900/80 px-4 py-2 text-sm text-white backdrop-blur">
        {getZoomLabel(zoomLevel)} · Zoom {zoomLevel}
      </div>
    </div>
  );
}
