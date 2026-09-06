/** Product capability matrix. Statuses match provenance data_status plus EXPERIMENTAL. */

export const CAPABILITIES = [
  {
    id: "current_flood_map",
    label: "Current flood map",
    status: "PARTIAL",
    note: "Physics or scenario overlay after a completed job. Otherwise no current flood raster.",
  },
  {
    id: "forecast",
    label: "Forecast",
    status: "PARTIAL",
    note: "Heuristic 6–72h points are DEMO (not spatial maps). Physics baseline is a short SWE burst. Validated 6–72h AI flood maps UNAVAILABLE.",
  },
  {
    id: "flood_depth",
    label: "Flood depth",
    status: "PARTIAL",
    note: "Available only on a completed physics/scenario artifact. Not fabricated.",
  },
  {
    id: "river_level",
    label: "River level",
    status: "DEMO",
    note: "DEMO gauge series when FLOODLENS_DEMO_FIXTURES=1. Never REAL or LIVE. Tests keep UNAVAILABLE.",
  },
  {
    id: "river_discharge",
    label: "River discharge",
    status: "DEMO",
    note: "DEMO discharge series when fixtures are on. Never a live gauge feed.",
  },
  {
    id: "rainfall",
    label: "Rainfall overlay",
    status: "DEMO",
    note: "DEMO point/uniform field and heatmap. Not a radar grid.",
  },
  {
    id: "terrain",
    label: "Terrain / DEM preview",
    status: "DEMO",
    note: "DEMO hillshade PNG only. Not a GeoTIFF DEM and not passed to the solver.",
  },
  {
    id: "population_exposure",
    label: "Population exposure",
    status: "DEMO",
    note: "DEMO exposure totals when fixtures are on. Not an authoritative census raster.",
  },
  {
    id: "infrastructure",
    label: "Infrastructure",
    status: "PARTIAL",
    note: "OSM points/lines when ingested; bbox-capped. Per-feature flood depth NOT_COMPUTED unless impact ran.",
  },
  {
    id: "scenario_simulation",
    label: "Scenario simulation",
    status: "SIMULATED",
    note: "SWE rainfall-multiplier jobs. River-boundary coupling is not enabled.",
  },
  {
    id: "ai_forecast",
    label: "AI forecast (AOI)",
    status: "PARTIAL",
    note: "AOI GBDT is a validated scalar AOI task when catalog says VALIDATED. Not an AI flood map.",
  },
  {
    id: "ai_spatial",
    label: "Spatial AI flood map",
    status: "UNAVAILABLE",
    note: "NOT_VALIDATED. POST /api/v1/forecast/ai-spatial stays UNAVAILABLE.",
  },
  {
    id: "physics_simulation",
    label: "Physics simulation",
    status: "SIMULATED",
    note: "Short SWE burst, not 24h inundation.",
  },
  {
    id: "uncertainty",
    label: "Uncertainty",
    status: "PARTIAL",
    note: "Heuristic interval/confidence_kind when present. Not a calibrated spatial CI.",
  },
  {
    id: "historical_replay",
    label: "Historical replay",
    status: "PARTIAL",
    note: "One DEMO paired event can show forecast-vs-reality metrics. Spatial AI stays NOT_VALIDATED. EMSR extents often null.",
  },
  {
    id: "evacuation_planning",
    label: "Evacuation planning",
    status: "PARTIAL",
    note: "DEMO planning polylines when fixtures are on. Not an official order. Travel time stays UNAVAILABLE.",
  },
  {
    id: "resources",
    label: "Resource inventories",
    status: "DEMO",
    note: "DEMO RESOURCE INVENTORY counts when fixtures are on. Planning estimates stay UNAVAILABLE.",
  },
  {
    id: "reports",
    label: "Reports",
    status: "PARTIAL",
    note: "JSON region reports. Population may be DEMO; official evacuation order stays false.",
  },
  {
    id: "alerts",
    label: "Alerts",
    status: "PARTIAL",
    note: "In-app evaluate against risk/probability. Not an operational warning service.",
  },
  {
    id: "ai_assistant",
    label: "AI assistant",
    status: "PARTIAL",
    note: "Tool-calling only. Does not invent numbers.",
  },
];

export function capabilityById(id) {
  return CAPABILITIES.find((row) => row.id === id);
}
