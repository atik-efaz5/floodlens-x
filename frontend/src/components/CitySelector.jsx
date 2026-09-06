import { useEffect, useState } from "react";
import { fetchCities, fetchCity } from "../services/cityRegistry";

/**
 * City selector dropdown component.
 *
 * @param {Object} props - Component props
 * @param {string} props.selectedCityId - Currently selected city ID
 * @param {Function} props.onCityChange - Callback when city selection changes
 * @returns {JSX.Element} Rendered component
 */
export default function CitySelector({
  selectedCityId = "sunamganj",
  onCityChange,
}) {
  const [cities, setCities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadCities = async () => {
      try {
        setLoading(true);
        setError(null);
        const citiesList = await fetchCities();
        setCities(citiesList);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    loadCities();
  }, []);

  const handleChange = async (event) => {
    const cityId = event.target.value;
    try {
      const cityData = await fetchCity(cityId);
      if (onCityChange) {
        onCityChange(cityData.city, cityData.scenarios);
      }
    } catch (err) {
      setError(err.message);
    }
  };

  if (loading) {
    return (
      <div className="text-sm text-slate-400">
        Loading cities...
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor="city-selector" className="text-sm font-semibold text-slate-400">
        Select City
      </label>
      <select
        id="city-selector"
        value={selectedCityId}
        onChange={handleChange}
        className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 transition hover:border-slate-600 focus:border-flood-500 focus:outline-none"
      >
        {cities.map((city) => (
          <option key={city.city_id} value={city.city_id}>
            {city.name} ({city.region})
          </option>
        ))}
      </select>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}
