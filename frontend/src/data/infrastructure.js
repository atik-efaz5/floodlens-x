export const FUTURE_ROADS_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "Sunamganj Ring Road (Planned)", status: "planned" },
      geometry: {
        type: "LineString",
        coordinates: [
          [91.30, 25.02],
          [91.36, 25.04],
          [91.42, 25.03],
          [91.45, 24.98],
        ],
      },
    },
    {
      type: "Feature",
      properties: { name: "Haor Access Corridor", status: "planned" },
      geometry: {
        type: "LineString",
        coordinates: [
          [91.22, 25.08],
          [91.28, 25.02],
          [91.34, 24.94],
        ],
      },
    },
    {
      type: "Feature",
      properties: { name: "Derai Connector", status: "planned" },
      geometry: {
        type: "LineString",
        coordinates: [
          [91.34, 24.92],
          [91.38, 24.88],
          [91.41, 24.84],
        ],
      },
    },
  ],
};

export const CRITICAL_FACILITIES_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "Sunamganj District Hospital", category: "hospital" },
      geometry: { type: "Point", coordinates: [91.396, 25.067] },
    },
    {
      type: "Feature",
      properties: { name: "Cyclone Shelter Alpha", category: "shelter" },
      geometry: { type: "Point", coordinates: [91.33, 24.97] },
    },
    {
      type: "Feature",
      properties: { name: "Substation North", category: "power" },
      geometry: { type: "Point", coordinates: [91.37, 25.05] },
    },
    {
      type: "Feature",
      properties: { name: "Emergency Operations Center", category: "shelter" },
      geometry: { type: "Point", coordinates: [91.35, 24.93] },
    },
  ],
};

export const RISK_ZONES_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { risk: "high", label: "Low-lying Haor Depression" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [91.28, 24.86],
            [91.40, 24.86],
            [91.42, 24.94],
            [91.30, 24.96],
            [91.28, 24.86],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { risk: "medium", label: "River Corridor Exposure" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [91.32, 24.98],
            [91.38, 24.98],
            [91.39, 25.04],
            [91.31, 25.03],
            [91.32, 24.98],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { risk: "low", label: "Elevated Foothill Fringe" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [91.24, 25.02],
            [91.30, 25.02],
            [91.31, 25.08],
            [91.25, 25.07],
            [91.24, 25.02],
          ],
        ],
      },
    },
  ],
};

export const FACILITY_COLORS = {
  hospital: "#ef4444",
  shelter: "#22c55e",
  power: "#f59e0b",
};

export const RISK_COLORS = {
  high: "#dc2626",
  medium: "#f59e0b",
  low: "#84cc16",
};

const DHAKA_FUTURE_ROADS_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "Dhaka Eastern Bypass (Planned)", status: "planned" },
      geometry: {
        type: "LineString",
        coordinates: [
          [90.45, 23.72],
          [90.52, 23.78],
          [90.58, 23.88],
          [90.62, 23.98],
        ],
      },
    },
    {
      type: "Feature",
      properties: { name: "Buriganga Flood Corridor", status: "planned" },
      geometry: {
        type: "LineString",
        coordinates: [
          [90.22, 23.68],
          [90.32, 23.70],
          [90.40, 23.74],
        ],
      },
    },
  ],
};

const DHAKA_CRITICAL_FACILITIES_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "Dhaka Medical College Hospital", category: "hospital" },
      geometry: { type: "Point", coordinates: [90.395, 23.726] },
    },
    {
      type: "Feature",
      properties: { name: "Kamalapur Shelter", category: "shelter" },
      geometry: { type: "Point", coordinates: [90.426, 23.732] },
    },
    {
      type: "Feature",
      properties: { name: "Gulshan Grid Station", category: "power" },
      geometry: { type: "Point", coordinates: [90.415, 23.792] },
    },
  ],
};

const DHAKA_RISK_ZONES_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { risk: "high", label: "Low-lying Eastern Wetlands" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [90.48, 23.72],
            [90.68, 23.72],
            [90.70, 23.88],
            [90.50, 23.90],
            [90.48, 23.72],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { risk: "medium", label: "Buriganga Corridor" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [90.22, 23.66],
            [90.38, 23.66],
            [90.40, 23.76],
            [90.24, 23.76],
            [90.22, 23.66],
          ],
        ],
      },
    },
  ],
};

const SYLHET_FUTURE_ROADS_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "Sylhet Ring Road (Planned)", status: "planned" },
      geometry: {
        type: "LineString",
        coordinates: [
          [91.72, 24.88],
          [91.86, 24.94],
          [91.98, 24.90],
          [92.08, 24.78],
        ],
      },
    },
    {
      type: "Feature",
      properties: { name: "Surma Access Link", status: "planned" },
      geometry: {
        type: "LineString",
        coordinates: [
          [91.78, 24.70],
          [91.88, 24.78],
          [91.96, 24.84],
        ],
      },
    },
  ],
};

const SYLHET_CRITICAL_FACILITIES_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "Sylhet MAG Osmani Medical College", category: "hospital" },
      geometry: { type: "Point", coordinates: [91.868, 24.901] },
    },
    {
      type: "Feature",
      properties: { name: "Osmani Shelter", category: "shelter" },
      geometry: { type: "Point", coordinates: [91.87, 24.86] },
    },
    {
      type: "Feature",
      properties: { name: "Kumargaon Substation", category: "power" },
      geometry: { type: "Point", coordinates: [91.92, 24.94] },
    },
  ],
};

const SYLHET_RISK_ZONES_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { risk: "high", label: "Surma Floodplain" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [91.70, 24.72],
            [91.95, 24.72],
            [91.98, 24.86],
            [91.72, 24.88],
            [91.70, 24.72],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { risk: "medium", label: "Haor Fringe East" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [92.00, 24.78],
            [92.18, 24.78],
            [92.20, 24.96],
            [92.02, 24.98],
            [92.00, 24.78],
          ],
        ],
      },
    },
  ],
};

export const CITY_INFRASTRUCTURE = {
  sunamganj: {
    future_roads: FUTURE_ROADS_GEOJSON,
    critical_facilities: CRITICAL_FACILITIES_GEOJSON,
    risk_zones: RISK_ZONES_GEOJSON,
  },
  dhaka: {
    future_roads: DHAKA_FUTURE_ROADS_GEOJSON,
    critical_facilities: DHAKA_CRITICAL_FACILITIES_GEOJSON,
    risk_zones: DHAKA_RISK_ZONES_GEOJSON,
  },
  sylhet: {
    future_roads: SYLHET_FUTURE_ROADS_GEOJSON,
    critical_facilities: SYLHET_CRITICAL_FACILITIES_GEOJSON,
    risk_zones: SYLHET_RISK_ZONES_GEOJSON,
  },
};

export function getCityInfrastructure(cityId) {
  return CITY_INFRASTRUCTURE[cityId] || CITY_INFRASTRUCTURE.sunamganj;
}
