const API = "";

export async function platformFetch(path, options = {}) {
  const role = options.role || localStorage.getItem("floodlens_role") || "general";
  const headers = {
    ...(options.headers || {}),
    Authorization: `Bearer demo.${role}`,
  };
  const response = await fetch(`${API}${path}`, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = data.detail?.error_code || data.detail || `Request failed (${response.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return data;
}

export function fetchStatus(cityId) {
  return platformFetch(`/api/v1/status?city_id=${encodeURIComponent(cityId)}`);
}

export function fetchForecast(cityId) {
  return platformFetch(`/api/v1/forecast?city_id=${encodeURIComponent(cityId)}`);
}

export function fetchCommand(cityId) {
  return platformFetch(`/api/v1/command?city_id=${encodeURIComponent(cityId)}`);
}

export function fetchDataSources(cityId) {
  return platformFetch(`/api/v1/data-sources?city_id=${encodeURIComponent(cityId)}`);
}

export function fetchInfrastructure(cityId, { bbox, type, limit = 400, offset = 0 } = {}) {
  const params = new URLSearchParams({
    city_id: cityId,
    limit: String(limit),
    offset: String(offset),
  });
  if (bbox) {
    params.set("bbox", bbox);
  }
  if (type) {
    params.set("type", type);
  }
  return platformFetch(`/api/v1/infrastructure?${params.toString()}`);
}

export function postChat(message, cityId, context = {}) {
  return platformFetch("/api/v1/assistant/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      city_id: cityId,
      river_id: context.selected_river || context.river_id || "buriganga",
      context,
      baseline_id: context.baseline_id || undefined,
      scenario_id: context.scenario_id || undefined,
      job_id: context.selected_job || undefined,
    }),
  });
}

export function postReport(cityId, { baselineJob, scenarioJob, eventId, mapState } = {}) {
  const params = new URLSearchParams({ city_id: cityId });
  if (baselineJob) params.set("baseline_job", baselineJob);
  if (scenarioJob) params.set("scenario_job", scenarioJob);
  if (eventId) params.set("event_id", eventId);
  return platformFetch(`/api/v1/reports?${params.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ map_state: mapState || null }),
  });
}

export function fetchJob(jobId) {
  return platformFetch(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
}

export function postPhysicsForecast(cityId, extra = {}) {
  return platformFetch("/api/v1/forecast/physics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      city_id: cityId,
      kind: "physics_forecast",
      nx: 12,
      ny: 12,
      duration_seconds: 0.3,
      steps: 1,
      allow_synthetic_dem: true,
      ...extra,
    }),
  });
}

export function postScenarioJob(cityId, extra = {}) {
  return platformFetch("/api/v1/scenarios", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      city_id: cityId,
      rainfall_multiplier: 1.3,
      river_level_delta_m: 0,
      nx: 12,
      ny: 12,
      duration_seconds: 0.3,
      steps: 1,
      allow_synthetic_dem: true,
      ...extra,
    }),
  });
}

export function fetchScenarioCapabilities() {
  return platformFetch("/api/v1/scenarios/capabilities");
}

export function fetchScenarioBaseline(cityId) {
  return platformFetch(`/api/v1/scenarios/baseline?city_id=${encodeURIComponent(cityId)}`);
}

export function fetchScenarioHistory(cityId) {
  return platformFetch(`/api/v1/scenarios/history?city_id=${encodeURIComponent(cityId)}`);
}

export function fetchScenarioWorkspace(cityId, { baselineJob, scenarioJob } = {}) {
  const params = new URLSearchParams({ city_id: cityId });
  if (baselineJob) params.set("baseline_job", baselineJob);
  if (scenarioJob) params.set("scenario_job", scenarioJob);
  return platformFetch(`/api/v1/scenarios/workspace?${params.toString()}`);
}

export function fetchScenarioDifference(baselineJob, scenarioJob) {
  const params = new URLSearchParams({
    baseline_job: baselineJob,
    scenario_job: scenarioJob,
  });
  return platformFetch(`/api/v1/scenarios/difference?${params.toString()}`);
}

export function fetchCausalChain(cityId, jobId) {
  const params = new URLSearchParams({ city_id: cityId });
  if (jobId) params.set("job_id", jobId);
  return platformFetch(`/api/v1/scenarios/causal-chain?${params.toString()}`);
}

export function compareJobs(jobIds) {
  return platformFetch("/api/v1/scenarios/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_ids: jobIds }),
  });
}

export function fetchFloodStates(cityId, horizonHours) {
  const params = new URLSearchParams({ city_id: cityId });
  if (horizonHours != null) {
    params.set("horizon_hours", String(horizonHours));
  }
  return platformFetch(`/api/v1/flood-states?${params.toString()}`);
}

export function artifactOverlayUrl(artifactId) {
  return `/api/v1/artifacts/${encodeURIComponent(artifactId)}/overlay.png`;
}

export function fetchArtifactSummary(artifactId) {
  return platformFetch(`/api/v1/artifacts/${encodeURIComponent(artifactId)}/summary`);
}

export function fetchRiverState(riverId) {
  return platformFetch(`/api/v1/rivers/${encodeURIComponent(riverId)}/state`);
}

export function fetchRiver(riverId) {
  return platformFetch(`/api/v1/rivers/${encodeURIComponent(riverId)}`);
}

export function fetchRiverGraph(riverId) {
  return platformFetch(`/api/v1/rivers/${encodeURIComponent(riverId)}/graph`);
}

export function fetchRiverObservations(riverId) {
  return platformFetch(`/api/v1/rivers/${encodeURIComponent(riverId)}/observations`);
}

export function fetchRiverOverview(riverId) {
  return platformFetch(`/api/v1/rivers/${encodeURIComponent(riverId)}/overview`);
}

export function fetchRiverSearch(query, cityId) {
  const params = new URLSearchParams({ q: query, limit: "20" });
  if (cityId) {
    params.set("city_id", cityId);
  }
  return platformFetch(`/api/v1/rivers/search?${params.toString()}`);
}

export function fetchRiverNeighbors(riverId, segmentId) {
  return platformFetch(
    `/api/v1/rivers/${encodeURIComponent(riverId)}/segments/${encodeURIComponent(segmentId)}/neighbors`
  );
}

export function fetchRiverSegment(riverId, segmentId) {
  return platformFetch(
    `/api/v1/rivers/${encodeURIComponent(riverId)}/segments/${encodeURIComponent(segmentId)}`
  );
}

export function fetchRegion(cityId) {
  return platformFetch(`/api/v1/regions/${encodeURIComponent(cityId)}`);
}

export function fetchModels() {
  return platformFetch("/api/v1/models");
}

export function fetchModel(modelId) {
  return platformFetch(`/api/v1/models/${encodeURIComponent(modelId)}`);
}

export function postAiForecast(cityId) {
  return platformFetch("/api/v1/forecast/ai", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ city_id: cityId }),
  });
}

export function postAiSpatialForecast(cityId) {
  return platformFetch("/api/v1/forecast/ai-spatial", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ city_id: cityId }),
  });
}

export function fetchExperiments() {
  return platformFetch("/api/v1/experiments");
}

export function fetchResearchCompare() {
  return platformFetch("/api/v1/research/compare");
}

export function fetchResearchOverview() {
  return platformFetch("/api/v1/research/overview");
}

export function fetchResearchInventory() {
  return platformFetch("/api/v1/research/inventory");
}

export function fetchResearchAi() {
  return platformFetch("/api/v1/research/ai");
}

export function fetchResearchExperiments() {
  return platformFetch("/api/v1/research/experiments");
}

export function fetchResearchExperiment(id) {
  return platformFetch(`/api/v1/research/experiments/${encodeURIComponent(id)}`);
}

export function runResearchSuite(suite, extra = {}) {
  return platformFetch("/api/v1/research/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ suite, ...extra }),
  });
}

export function postResearchReport(experimentId) {
  const query = experimentId ? `?experiment_id=${encodeURIComponent(experimentId)}` : "";
  return platformFetch(`/api/v1/research/reports${query}`, { method: "POST" });
}

export function fetchRainfall(cityId, kind) {
  const params = new URLSearchParams({ city_id: cityId, variable: "precipitation_mm" });
  if (kind) {
    params.set("kind", kind);
  }
  return platformFetch(`/api/v1/observations?${params.toString()}`);
}

export function fetchTerrain(cityId) {
  const params = new URLSearchParams({ city_id: cityId });
  return platformFetch(`/api/v1/terrain?${params.toString()}`);
}

export function fetchJobs() {
  return platformFetch("/api/v1/jobs");
}

export function evaluateAlerts(cityId) {
  return platformFetch(`/api/v1/alerts/evaluate?city_id=${encodeURIComponent(cityId)}`);
}

export function fetchAlertMetrics(cityId) {
  const query = cityId ? `?city_id=${encodeURIComponent(cityId)}` : "";
  return platformFetch(`/api/v1/alerts/metrics${query}`);
}

export function fetchAlerts() {
  return platformFetch("/api/v1/alerts");
}

export function postAlert(payload) {
  return platformFetch("/api/v1/alerts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function acknowledgeAlert(alertId) {
  return platformFetch(`/api/v1/alerts/${encodeURIComponent(alertId)}/acknowledge`, { method: "POST" });
}

export function fetchAlertHistory(alertId) {
  return platformFetch(`/api/v1/alerts/${encodeURIComponent(alertId)}/history`);
}

export function fetchLocations() {
  return platformFetch("/api/v1/locations");
}

export function postLocation(payload) {
  return platformFetch("/api/v1/locations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function patchLocation(locationId, payload) {
  return platformFetch(`/api/v1/locations/${encodeURIComponent(locationId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deleteLocation(locationId) {
  return platformFetch(`/api/v1/locations/${encodeURIComponent(locationId)}`, { method: "DELETE" });
}

export function restoreLocation(locationId) {
  return platformFetch(`/api/v1/locations/${encodeURIComponent(locationId)}/restore`);
}

export function fetchReports() {
  return platformFetch("/api/v1/reports");
}

export function fetchReport(reportId, format) {
  const query = format ? `?format=${encodeURIComponent(format)}` : "";
  if (format === "pdf" || format === "csv") {
    const role = localStorage.getItem("floodlens_role") || "general";
    return fetch(`/api/v1/reports/${encodeURIComponent(reportId)}${query}`, {
      headers: { Authorization: `Bearer demo.${role}` },
    });
  }
  return platformFetch(`/api/v1/reports/${encodeURIComponent(reportId)}${query}`);
}

export function postShare(reportId, visibility = "private") {
  return platformFetch(`/api/v1/shares/${encodeURIComponent(reportId)}?visibility=${encodeURIComponent(visibility)}`, {
    method: "POST",
  });
}

export function fetchShare(shareId) {
  return platformFetch(`/api/v1/shares/${encodeURIComponent(shareId)}`);
}

export function revokeShare(shareId) {
  return platformFetch(`/api/v1/shares/${encodeURIComponent(shareId)}/revoke`, { method: "POST" });
}

export function fetchHealth() {
  return platformFetch("/api/v1/health");
}

export function fetchRivers(cityId, { bbox, limit } = {}) {
  const params = new URLSearchParams();
  if (cityId) {
    params.set("city_id", cityId);
  }
  if (bbox) {
    params.set("bbox", bbox);
  }
  if (limit != null) {
    params.set("limit", String(limit));
  }
  const query = params.toString();
  return platformFetch(`/api/v1/rivers${query ? `?${query}` : ""}`);
}

export function fetchLayerCatalog(cityId) {
  return platformFetch(`/api/v1/catalog/layers?city_id=${encodeURIComponent(cityId)}`);
}

export function postImpact(cityId, jobId) {
  return platformFetch("/api/v1/impact/assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ city_id: cityId, job_id: jobId || null }),
  });
}

function impactQuery(cityId, { jobId, category, bbox, limit } = {}) {
  const params = new URLSearchParams({ city_id: cityId });
  if (jobId) params.set("job_id", jobId);
  if (category) params.set("category", category);
  if (bbox) params.set("bbox", bbox);
  if (limit != null) params.set("limit", String(limit));
  return params.toString();
}

export function fetchImpact(cityId, options) {
  return platformFetch(`/api/v1/impact?${impactQuery(cityId, options)}`);
}

export function fetchImpactInfrastructure(cityId, options) {
  return platformFetch(`/api/v1/impact/infrastructure?${impactQuery(cityId, options)}`);
}

export function fetchImpactShelters(cityId, options) {
  return platformFetch(`/api/v1/impact/shelters?${impactQuery(cityId, options)}`);
}

export function fetchImpactEvacuation(cityId, options) {
  return platformFetch(`/api/v1/impact/evacuation?${impactQuery(cityId, options)}`);
}

export function fetchImpactResources(cityId, options) {
  return platformFetch(`/api/v1/impact/resources?${impactQuery(cityId, options)}`);
}

export function fetchHistoryEvents(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value != null && value !== "") {
      params.set(key, String(value));
    }
  });
  const query = params.toString();
  return platformFetch(`/api/v1/history/events${query ? `?${query}` : ""}`);
}

export function fetchHistoryEvent(eventId) {
  return platformFetch(`/api/v1/history/events/${encodeURIComponent(eventId)}`);
}

export function fetchHistoryObservations(eventId) {
  return platformFetch(`/api/v1/history/events/${encodeURIComponent(eventId)}/observations`);
}

export function fetchHistoryPredictions(eventId) {
  return platformFetch(`/api/v1/history/events/${encodeURIComponent(eventId)}/predictions`);
}

export function fetchHistoryCompare(eventId, predictionId) {
  const params = new URLSearchParams();
  if (predictionId) params.set("prediction_id", predictionId);
  const query = params.toString();
  return platformFetch(
    `/api/v1/history/events/${encodeURIComponent(eventId)}/compare${query ? `?${query}` : ""}`
  );
}

export function postHistoryReport(eventId, cityId) {
  const params = new URLSearchParams();
  if (cityId) params.set("city_id", cityId);
  const query = params.toString();
  return platformFetch(
    `/api/v1/history/events/${encodeURIComponent(eventId)}/report${query ? `?${query}` : ""}`,
    { method: "POST" }
  );
}

export function fetchModelPerformance(modelId) {
  if (modelId) {
    return platformFetch(`/api/v1/models/${encodeURIComponent(modelId)}`);
  }
  return platformFetch("/api/v1/models/performance");
}
