const API_BASE = "";

export async function fetchScenarioMetadata() {
  const response = await fetch(`${API_BASE}/api/scenario/metadata`);
  if (!response.ok) {
    throw new Error(`Failed to load metadata (${response.status})`);
  }
  return response.json();
}

export async function runScenario(payload) {
  const response = await fetch(`${API_BASE}/api/scenario/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Scenario run failed (${response.status})`);
  }
  return response.json();
}

export async function inspectCell(latitude, longitude, context = {}) {
  const params = new URLSearchParams({
    lat: String(latitude),
    lon: String(longitude),
    city_id: context.cityId || "",
    scenario_id: context.scenarioId || "",
  });
  if (context.time !== undefined && context.time !== null) {
    params.set("time", String(context.time));
  }
  const response = await fetch(`${API_BASE}/api/cell/inspect?${params}`);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    const payload = detail.detail;
    const error = new Error(
      payload && typeof payload === "object" && payload.message
        ? payload.message
        : detail.detail || `Cell inspect failed (${response.status})`
    );
    if (payload && typeof payload === "object") {
      error.errorCode = payload.error_code;
    }
    throw error;
  }
  return response.json();
}

export async function fetchScenarioTimeline(cityId, scenarioId) {
  const params = new URLSearchParams({ city_id: cityId });
  const response = await fetch(
    `${API_BASE}/api/scenario/${encodeURIComponent(scenarioId)}/timeline?${params}`
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(
      (detail && detail.message) || data.detail || `Timeline request failed (${response.status})`
    );
  }
  return data;
}

export async function fetchScenarioSnapshot(cityId, scenarioId, time) {
  const params = new URLSearchParams({
    city_id: cityId,
    time: String(time),
  });
  const response = await fetch(
    `${API_BASE}/api/scenario/${encodeURIComponent(scenarioId)}/snapshot?${params}`
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(
      (detail && detail.message) || data.detail || `Snapshot request failed (${response.status})`
    );
  }
  return data;
}

export async function searchLocations(query) {
  const params = new URLSearchParams({ q: query });
  const response = await fetch(`${API_BASE}/api/geocode/search?${params}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Location search failed (${response.status})`);
  }
  return data;
}

export async function compareScenarios(payload) {
  const response = await fetch(`${API_BASE}/api/scenario/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    if (detail && typeof detail === "object" && detail.message) {
      throw new Error(detail.message);
    }
    throw new Error(detail || `Scenario compare failed (${response.status})`);
  }
  return data;
}
