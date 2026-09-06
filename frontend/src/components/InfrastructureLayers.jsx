import { CircleMarker, GeoJSON, Polyline } from "react-leaflet";
import { FACILITY_COLORS, RISK_COLORS, getCityInfrastructure } from "../data/infrastructure";

function roadStyle() {
  return {
    color: "#38bdf8",
    weight: 4,
    opacity: 0.85,
    dashArray: "8 6",
  };
}

function riskStyle(feature) {
  const risk = feature?.properties?.risk || "low";
  return {
    color: RISK_COLORS[risk],
    fillColor: RISK_COLORS[risk],
    fillOpacity: 0.22,
    weight: 1.5,
  };
}

export default function InfrastructureLayers({ enabledLayers, cityId }) {
  const layers = getCityInfrastructure(cityId);

  return (
    <>
      {enabledLayers.future_roads &&
        layers.future_roads.features.map((feature) => (
          <Polyline
            key={feature.properties.name}
            positions={feature.geometry.coordinates.map(([lng, lat]) => [lat, lng])}
            pathOptions={roadStyle()}
          />
        ))}

      {enabledLayers.risk_zones && (
        <GeoJSON data={layers.risk_zones} style={riskStyle} />
      )}

      {enabledLayers.critical_facilities &&
        layers.critical_facilities.features.map((feature) => {
          const [lng, lat] = feature.geometry.coordinates;
          const category = feature.properties.category;
          return (
            <CircleMarker
              key={feature.properties.name}
              center={[lat, lng]}
              radius={8}
              pathOptions={{
                color: "#ffffff",
                weight: 2,
                fillColor: FACILITY_COLORS[category] || "#f97316",
                fillOpacity: 0.95,
              }}
            />
          );
        })}
    </>
  );
}
