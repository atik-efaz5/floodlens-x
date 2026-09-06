export const COMPARISON_MODES = [
  { id: "SIDE_BY_SIDE", label: "Side-by-side" },
  { id: "SWIPE", label: "Swipe" },
  { id: "DIFFERENCE", label: "Difference" },
];

export const COMPARISON_LAYERS = [
  { id: "depth", label: "Depth" },
  { id: "velocity", label: "Velocity" },
  { id: "max_depth", label: "Max Depth" },
  { id: "flood_extent", label: "Flood Extent" },
];

export function canCompareScenarios(cityId, scenarioA, scenarioB) {
  if (!cityId || !scenarioA || !scenarioB) {
    return false;
  }
  return (
    scenarioA.cityId === cityId &&
    scenarioB.cityId === cityId &&
    scenarioA.scenarioId !== scenarioB.scenarioId
  );
}

export function syncViewport(sourceViewport) {
  return {
    center: sourceViewport.center,
    zoom: sourceViewport.zoom,
  };
}
