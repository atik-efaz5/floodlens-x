"""Pre-configured city metadata for supported regions."""

from floodlens.application.city_registry import CityRegistry
from floodlens.application.geospatial import (
    CityMetadata,
    GeographicBounds,
    GridReference,
    ScenarioMetadataV2,
    CenterCoordinates,
    TimeRange,
    DEFAULT_VISUALIZATION_LAYERS,
)


def create_city_registry() -> CityRegistry:
    """Initialize registry with Sunamganj, Dhaka, and Sylhet cities.

    Returns:
        Populated CityRegistry instance.
    """
    registry = CityRegistry()

    # Sunamganj - existing city with validated bounds and grid
    sunamganj = CityMetadata(
        city_id="sunamganj",
        name="Sunamganj",
        country="Bangladesh",
        region="Sunamganj District",
        center_lat=24.95,
        center_lon=91.35,
        bounds=GeographicBounds(
            west=91.20,
            south=24.80,
            east=91.50,
            north=25.10,
        ),
        crs="EPSG:4326",
        default_zoom=11,
        min_zoom=8,
        max_zoom=16,
        supported_layers=DEFAULT_VISUALIZATION_LAYERS,
        grid_metadata=GridReference(
            nx=50,
            ny=50,
            dx=240.0,  # ~0.3 deg * 800 m/deg
            dy=240.0,
            origin_x=91.20,
            origin_y=24.80,
            crs="EPSG:4326",
        ),
        is_default_city=True,
    )
    registry.register_city(sunamganj)

    # Dhaka - Bangladesh capital
    dhaka = CityMetadata(
        city_id="dhaka",
        name="Dhaka",
        country="Bangladesh",
        region="Dhaka Division",
        center_lat=23.8103,
        center_lon=90.4125,
        bounds=GeographicBounds(
            west=90.0,
            south=23.5,
            east=90.8,
            north=24.1,
        ),
        crs="EPSG:4326",
        default_zoom=12,
        min_zoom=8,
        max_zoom=16,
        supported_layers=DEFAULT_VISUALIZATION_LAYERS,
        grid_metadata=GridReference(
            nx=50,
            ny=50,
            dx=160.0,  # ~0.2 deg * 800 m/deg
            dy=160.0,
            origin_x=90.0,
            origin_y=23.5,
            crs="EPSG:4326",
        ),
        is_default_city=False,
    )
    registry.register_city(dhaka)

    # Sylhet - North-east Bangladesh region
    sylhet = CityMetadata(
        city_id="sylhet",
        name="Sylhet",
        country="Bangladesh",
        region="Sylhet Division",
        center_lat=24.8,
        center_lon=91.9,
        bounds=GeographicBounds(
            west=91.5,
            south=24.4,
            east=92.3,
            north=25.2,
        ),
        crs="EPSG:4326",
        default_zoom=11,
        min_zoom=8,
        max_zoom=16,
        supported_layers=DEFAULT_VISUALIZATION_LAYERS,
        grid_metadata=GridReference(
            nx=50,
            ny=50,
            dx=320.0,  # ~0.4 deg * 800 m/deg
            dy=320.0,
            origin_x=91.5,
            origin_y=24.4,
            crs="EPSG:4326",
        ),
        is_default_city=False,
    )
    registry.register_city(sylhet)

    _register_modeled_scenarios(registry)
    return registry


def _register_modeled_scenarios(registry: CityRegistry) -> None:
    """Register modeled scenario placeholders. Results are stored separately."""
    for city in registry.list_cities():
        for scenario_id, name, description in (
            (
                "moderate_rain",
                "Moderate Rain",
                "Modeled moderate-rainfall simulation. Not observationally validated.",
            ),
            (
                "heavy_rain",
                "Heavy Rain",
                "Modeled heavy-rainfall simulation. Not observationally validated.",
            ),
        ):
            registry.register_scenario(
                ScenarioMetadataV2(
                    scenario_id=scenario_id,
                    city_id=city.city_id,
                    name=name,
                    description=description,
                    bounds=city.bounds,
                    center=CenterCoordinates(
                        latitude=city.center_lat,
                        longitude=city.center_lon,
                        label=city.name,
                    ),
                    crs=city.crs,
                    time_range=TimeRange(start_seconds=0.0, end_seconds=0.0),
                    visualization_layers=DEFAULT_VISUALIZATION_LAYERS,
                    grid_metadata=city.grid_metadata,
                    modeled_status=True,
                    simulated_status=False,
                )
            )
