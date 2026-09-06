/** Explore URL hash state. Not a separate sharing product — restores Explore context. */

export const DEFAULT_LAYERS = {
  floodExtent: true,
  forecast: true,
  rivers: true,
  roads: true,
  hospitals: true,
  schools: true,
  bridges: true,
  critical: true,
  shelters: true,
  rainfall: false,
  terrain: false,
};

export function parseExploreHash(hash = typeof window !== "undefined" ? window.location.hash : "") {
  const raw = String(hash || "").replace(/^#/, "");
  if (!raw) {
    return null;
  }
  const params = new URLSearchParams(raw);
  const layers = { ...DEFAULT_LAYERS };
  const listed = params.get("layers");
  if (listed) {
    const enabled = new Set(listed.split(",").filter(Boolean));
    Object.keys(layers).forEach((key) => {
      layers[key] = enabled.has(key);
    });
  }
  const lat = params.get("lat");
  const lon = params.get("lon");
  const zoom = params.get("z");
  return {
    cityId: params.get("city") || null,
    view: params.get("view") || null,
    jobId: params.get("job") || null,
    latitude: lat != null && lat !== "" ? Number(lat) : null,
    longitude: lon != null && lon !== "" ? Number(lon) : null,
    zoom: zoom != null && zoom !== "" ? Number(zoom) : null,
    layers,
    filter: params.get("filter") || "all",
    riverId: params.get("river") || null,
  };
}

export function serializeExploreHash({
  cityId,
  view,
  jobId,
  latitude,
  longitude,
  zoom,
  layers = DEFAULT_LAYERS,
  filter = "all",
  riverId,
}) {
  const params = new URLSearchParams();
  if (cityId) {
    params.set("city", cityId);
  }
  if (view && view !== "explore") {
    params.set("view", view);
  }
  if (jobId) {
    params.set("job", jobId);
  }
  if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
    params.set("lat", latitude.toFixed(5));
    params.set("lon", longitude.toFixed(5));
  }
  if (Number.isFinite(zoom)) {
    params.set("z", String(Math.round(zoom)));
  }
  const on = Object.entries(layers)
    .filter(([, value]) => value)
    .map(([key]) => key);
  params.set("layers", on.join(","));
  if (filter && filter !== "all") {
    params.set("filter", filter);
  }
  if (riverId) {
    params.set("river", riverId);
  }
  return `#${params.toString()}`;
}

export function layersFromQuickFilter(filterId) {
  const allOn = { ...DEFAULT_LAYERS };
  if (!filterId || filterId === "all") {
    return allOn;
  }
  const next = {
    ...allOn,
    roads: false,
    hospitals: false,
    schools: false,
    bridges: false,
    critical: false,
    shelters: false,
  };
  if (filterId === "hospitals") next.hospitals = true;
  if (filterId === "schools") next.schools = true;
  if (filterId === "bridges") next.bridges = true;
  if (filterId === "roads") next.roads = true;
  if (filterId === "critical") next.critical = true;
  if (filterId === "shelters") next.shelters = true;
  next.rivers = true;
  return next;
}

export function typeFilterFromLayers(layers, quickFilter) {
  if (quickFilter && quickFilter !== "all") {
    const map = {
      hospitals: "hospital",
      schools: "school",
      bridges: "bridge",
      roads: "road",
      critical: "emergency",
      shelters: "shelter",
    };
    return map[quickFilter] || "";
  }
  const types = [];
  if (layers.hospitals) types.push("hospital");
  if (layers.schools) types.push("school");
  if (layers.bridges) types.push("bridge");
  if (layers.roads) types.push("road");
  if (layers.critical) types.push("emergency");
  if (layers.shelters) types.push("shelter");
  if (types.length === 1) {
    return types[0];
  }
  return "";
}
