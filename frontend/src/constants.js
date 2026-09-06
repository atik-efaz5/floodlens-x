export function getZoomLabel(zoom) {
  const levels = [
    { min: 0, max: 7, label: "Country" },
    { min: 8, max: 11, label: "City" },
    { min: 12, max: 15, label: "Neighborhood" },
    { min: 16, max: 22, label: "Street" },
  ];
  const level = levels.find((item) => zoom >= item.min && zoom <= item.max);
  return level ? level.label : "Overview";
}

export function formatTime(seconds) {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

export const FLOOD_LAYER_OPTIONS = [
  { id: "depth", label: "Flood Depth" },
  { id: "velocity", label: "Velocity" },
  { id: "max_depth", label: "Max Depth" },
  { id: "flood_extent", label: "Flood Extent" },
];

export const INFRA_LAYER_OPTIONS = [
  { id: "future_roads", label: "Future Roads" },
  { id: "critical_facilities", label: "Critical Facilities" },
  { id: "risk_zones", label: "Vulnerability / Risk Zones" },
];

export const DEFAULT_PARAMS = {
  nx: 30,
  ny: 30,
  rainfall_rate: 1.0e-5,
  duration_seconds: 5.0,
};
