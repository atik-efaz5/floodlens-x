/**
 * City registry service for fetching city metadata and managing city data.
 */

const API_BASE = "";

let citiesCache = null;

/**
 * Fetch all supported cities from the backend.
 * Results are cached in memory.
 *
 * @returns {Promise<Array>} Array of city metadata objects
 */
export async function fetchCities() {
  if (citiesCache) {
    return citiesCache;
  }

  const response = await fetch(`${API_BASE}/api/cities`);
  if (!response.ok) {
    throw new Error(`Failed to load cities (${response.status})`);
  }

  const data = await response.json();
  citiesCache = data.cities || [];
  return citiesCache;
}

/**
 * Fetch full metadata for a specific city including scenarios.
 *
 * @param {string} cityId - The city identifier
 * @returns {Promise<Object>} City metadata with scenarios
 */
export async function fetchCity(cityId) {
  const response = await fetch(`${API_BASE}/api/cities/${cityId}`);
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(`City ${cityId} not found`);
    }
    throw new Error(`Failed to load city metadata (${response.status})`);
  }

  return response.json();
}

/**
 * Get cached cities without fetching.
 * Returns null if cities have not been fetched yet.
 *
 * @returns {Array|null} Cached cities or null
 */
export function getCachedCities() {
  return citiesCache;
}

/**
 * Clear the cities cache.
 */
export function clearCitiesCache() {
  citiesCache = null;
}

/**
 * Find a city by ID from cached cities.
 *
 * @param {string} cityId - The city identifier
 * @returns {Object|undefined} City metadata or undefined if not found
 */
export function findCityInCache(cityId) {
  if (!citiesCache) return undefined;
  return citiesCache.find((city) => city.city_id === cityId);
}
