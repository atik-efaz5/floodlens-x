export function parseCoordinateQuery(query) {
  const match = query.trim().match(/^(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)$/);
  if (!match) {
    return null;
  }

  const first = Number(match[1]);
  const second = Number(match[2]);

  if (first >= -90 && first <= 90 && second >= -180 && second <= 180) {
    return {
      display_name: `${first.toFixed(4)}°, ${second.toFixed(4)}°`,
      latitude: first,
      longitude: second,
      place_type: "coordinates",
    };
  }

  if (second >= -90 && second <= 90 && first >= -180 && first <= 180) {
    return {
      display_name: `${second.toFixed(4)}°, ${first.toFixed(4)}°`,
      latitude: second,
      longitude: first,
      place_type: "coordinates",
    };
  }

  return null;
}

export function isWithinCityBounds(latitude, longitude, bounds) {
  if (!bounds) {
    return true;
  }
  return (
    latitude >= bounds.south &&
    latitude <= bounds.north &&
    longitude >= bounds.west &&
    longitude <= bounds.east
  );
}

export function selectSearchZoom(placeType, cityDefaultZoom = 12) {
  switch (placeType) {
    case "coordinates":
    case "neighbourhood":
    case "suburb":
      return Math.max(cityDefaultZoom + 1, 14);
    case "landmark":
    case "upazila":
      return Math.max(cityDefaultZoom, 12);
    case "city":
      return Math.max(cityDefaultZoom - 1, 10);
    case "country":
      return 6;
    case "river":
      return Math.max(cityDefaultZoom, 12);
    case "region":
      return Math.max(cityDefaultZoom - 1, 10);
    default:
      return cityDefaultZoom;
  }
}
