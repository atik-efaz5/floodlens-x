"""Canonical forecast-forcing schema and vintage integrity.

No model fitting. Does not treat ERA5/GloFAS reanalysis as a forecast issued at t0.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from floodlens.ml.leakage import parse_ts

# Availability categories. Do not collapse.
OBSERVED_AVAILABLE = "OBSERVED-AVAILABLE"  # A: known at/before t0 without depending on later obs
FORECAST_AVAILABLE = "FORECAST-AVAILABLE"  # B: product issued at/before t0, valid after t0
POST_T0_OBSERVATION = "POST-T0 OBSERVATION"  # C: observed/reanalysis after t0
UNAVAILABLE = "UNAVAILABLE"  # D
UNKNOWN = "UNKNOWN"  # E

# Product kinds (not the same as availability).
KIND_OBSERVED = "observed"
KIND_REANALYSIS = "reanalysis"
KIND_FORECAST = "forecast"
KIND_MODELLED = "modelled"
KIND_SIMULATED = "simulated"
KIND_DEMO = "demo"
KIND_UNAVAILABLE = "unavailable"

HORIZON_HOURS_192 = 192


def _iso(stamp: datetime) -> str:
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def issue_at_or_before_t0(issue_time: str, t0: str) -> bool:
    return parse_ts(issue_time) <= parse_ts(t0)


def cube_issue_192h(later_valid_at: str) -> str:
    """Track A cube issue time: valid_at − 192 h. Not Target B t0."""
    return _iso(parse_ts(later_valid_at) - timedelta(hours=HORIZON_HOURS_192))


@dataclass
class ForecastForcing:
    """One forcing field for one time window. Arrays stay out of JSON."""

    source: str
    provider: str
    issue_time: Optional[str]
    valid_start: str
    valid_end: str
    lead_time_hours: Optional[float]
    variable: str
    units: str
    spatial_resolution: str
    temporal_resolution: str
    coverage: str
    status: str
    kind: str
    availability: str
    provenance: Dict[str, Any] = field(default_factory=dict)
    acquired: bool = False
    filled: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def vintage_ok(self, t0: str) -> bool:
        if self.availability == FORECAST_AVAILABLE:
            if not self.issue_time:
                return False
            return issue_at_or_before_t0(self.issue_time, t0)
        if self.availability == POST_T0_OBSERVATION:
            return True  # allowed as explanation only, not as t0 input
        if self.issue_time and self.availability in {OBSERVED_AVAILABLE, FORECAST_AVAILABLE}:
            return issue_at_or_before_t0(self.issue_time, t0)
        return True


def classify_precip(*, window: str, kind: str, issue_time: Optional[str], t0: str) -> str:
    """window is pre_t0 | in_horizon. kind is reanalysis | forecast | observed."""
    if kind in {KIND_UNAVAILABLE, KIND_DEMO, KIND_SIMULATED}:
        return UNAVAILABLE if kind == KIND_UNAVAILABLE else UNKNOWN
    if window == "in_horizon":
        if kind == KIND_FORECAST:
            if issue_time and issue_at_or_before_t0(issue_time, t0):
                return FORECAST_AVAILABLE
            return POST_T0_OBSERVATION if issue_time else UNAVAILABLE
        return POST_T0_OBSERVATION
    if window == "pre_t0":
        if kind in {KIND_OBSERVED, KIND_REANALYSIS, KIND_MODELLED}:
            return OBSERVED_AVAILABLE
        if kind == KIND_FORECAST:
            return FORECAST_AVAILABLE if issue_time and issue_at_or_before_t0(issue_time, t0) else UNAVAILABLE
    return UNKNOWN


def reject_hindsight_forecast(record: ForecastForcing, t0: str) -> Optional[str]:
    """Return an error if a FORECAST-AVAILABLE record is actually post-t0."""
    if record.availability != FORECAST_AVAILABLE:
        return None
    if not record.issue_time:
        return "FORECAST-AVAILABLE record missing issue_time"
    if parse_ts(record.issue_time) > parse_ts(t0):
        return "forecast issue_time > t0 (hindsight)"
    if record.filled:
        return "forecast record was temporally filled"
    return None


# Phase 6.9A interval / feature statuses. Do not collapse with A–E availability codes.
FORECAST_VINTAGE = "FORECAST_VINTAGE"
MODELLED_STATE = "MODELLED_STATE"
OBSERVED_LOOKBACK = "OBSERVED_LOOKBACK"
POST_T0_OBSERVATION_STATUS = "POST_T0_OBSERVATION"

NWP_CYCLES_UTC = (0, 6, 12, 18)
TIGGE_ECMWF_CYCLES_UTC = (0, 12)
IFS_ISSUE_LATENCY_HOURS = 6.0
IFS_HRES_ARCHIVE_START = "2024-03-14T00:00:00Z"
IFS_HRES_DOCUMENTED_LEAD_HOURS = 240.0  # Open-Meteo Single Runs table: IFS HRES 10 days
COMPLETE_COVERAGE_EPS = 0.99
FORECAST_BENCHMARK_ELIGIBLE = frozenset({"FULL_CAUSAL", "PARTIAL_CAUSAL"})
TARGET_B_PRIMARY_LABEL = "NEWLY_FLOODED"


def causal_timestamp_violations(
    *,
    t0: str,
    t1: str,
    issue_time: Optional[str] = None,
    valid_times: Optional[Sequence[str]] = None,
    state_time: Optional[str] = None,
    era5_in_horizon_as_forecast: bool = False,
    future_glofas_as_forecast: bool = False,
    target_derived_features: bool = False,
    filled: bool = False,
) -> List[str]:
    """Return leakage reasons. Empty list means the record is causally admissible."""
    reasons: List[str] = []
    if issue_time and not issue_at_or_before_t0(issue_time, t0):
        reasons.append("forecast issue_time > t0")
    for valid in valid_times or []:
        if not valid_time_in_target_interval(valid, t0, t1):
            reasons.append(f"forecast valid_time not in (t0,t1]: {valid}")
    if state_time and not state_timestamp_at_or_before_t0(state_time, t0):
        reasons.append("glofas_state_time > t0")
    if era5_in_horizon_as_forecast:
        reasons.append("post-t0 ERA5 used as forecast forcing")
    if future_glofas_as_forecast:
        reasons.append("future GloFAS observations used as forecast forcing")
    if target_derived_features:
        reasons.append("target-derived features present")
    if filled:
        reasons.append("forecast record was temporally filled")
    return reasons


def valid_time_in_target_interval(valid_time: str, t0: str, t1: str) -> bool:
    """In-horizon forecast hours are (t0, t1]. Equal-t0 is lookback, not forecast forcing."""
    stamp = parse_ts(valid_time)
    return parse_ts(t0) < stamp <= parse_ts(t1)


def state_timestamp_at_or_before_t0(timestamp: str, t0: str) -> bool:
    return parse_ts(timestamp) <= parse_ts(t0)


def last_available_nwp_run(
    t0: str,
    *,
    latency_hours: float = IFS_ISSUE_LATENCY_HOURS,
    cycles: tuple = NWP_CYCLES_UTC,
) -> Optional[datetime]:
    """Latest cycle whose products are treated as issued (init + latency) at or before t0."""
    t0p = parse_ts(t0)
    cursor = t0p.replace(minute=0, second=0, microsecond=0)
    for _ in range(96):
        if cursor.hour in cycles:
            available_at = cursor + timedelta(hours=float(latency_hours))
            if available_at <= t0p:
                return cursor
        cursor = cursor - timedelta(hours=1)
    return None



# Candidate products. Acquired=False unless a file exists in this repo.
FORECAST_SOURCES: List[dict] = [
    {
        "id": "era5-land-open-meteo-lattice",
        "product_name": "ERA5-Land precipitation (Open-Meteo archive lattice)",
        "provider": "Open-Meteo / ECMWF ERA5-Land family",
        "forecast_type": KIND_REANALYSIS,
        "spatial_resolution": "~11 km (3×3 lattice, IDW to 64×64)",
        "temporal_resolution": "hourly",
        "forecast_issue_time": "none (reanalysis, not a run)",
        "forecast_lead_time": "n/a",
        "historical_archive": "2016-06-01 … 2024-08-31 in precip_lattice.json",
        "bangladesh_coverage": True,
        "precipitation_variables": ["precipitation_mm"],
        "licensing": "CC BY 4.0 (Open-Meteo); ERA5-Land Copernicus",
        "reproducibility": "HTTPS archive-api.open-meteo.com",
        "access_requirements": "none",
        "historical_forecasts_reconstructable": False,
        "existed_during_target_b_period": True,
        "acquired": True,
        "in_spatial_cube": True,
        "availability_pre_t0": OBSERVED_AVAILABLE,
        "availability_in_horizon": POST_T0_OBSERVATION,
        "note": "Hindsight. Rain in (t0,t1] is POST-T0 OBSERVATION, never a forecast input.",
        "source_url": "https://archive-api.open-meteo.com/v1/archive",
    },
    {
        "id": "open-meteo-previous-runs",
        "product_name": "Open-Meteo Previous Runs API",
        "provider": "Open-Meteo",
        "forecast_type": KIND_FORECAST,
        "spatial_resolution": "model-dependent (GFS ~25 km, ICON ~13 km, IFS varies)",
        "temporal_resolution": "hourly, fixed lead offsets 1–7 days",
        "forecast_issue_time": "implied by previous_dayN offset; not a full run catalogue",
        "forecast_lead_time": "1–7 days",
        "historical_archive": "most models from January 2024; GFS T2m from 2021 (not precip cube-wide)",
        "bangladesh_coverage": True,
        "precipitation_variables": ["precipitation / rain previous_day1…7"],
        "licensing": "CC BY 4.0",
        "reproducibility": "HTTPS previous-runs-api.open-meteo.com",
        "access_requirements": "none",
        "historical_forecasts_reconstructable": "partial (lead-offset series, not every initialisation)",
        "existed_during_target_b_period": "only 2024 events in the 15-event cube",
        "acquired": False,
        "in_spatial_cube": False,
        "availability_pre_t0": UNAVAILABLE,
        "availability_in_horizon": UNAVAILABLE,
        "max_lead_hours": 168,
        "archive_start": "2024-01-01",
        "note": "Lead cap 7 d is shorter than Target B median 12 d. Not acquired.",
        "source_url": "https://open-meteo.com/en/docs/previous-runs-api",
    },
    {
        "id": "open-meteo-historical-forecast",
        "product_name": "Open-Meteo Historical Forecast API",
        "provider": "Open-Meteo",
        "forecast_type": KIND_FORECAST,
        "spatial_resolution": "blended model grid",
        "temporal_resolution": "hourly",
        "forecast_issue_time": "not a single-run vintage; blended across updates",
        "forecast_lead_time": "short-range (first hours of each update)",
        "historical_archive": "~2021 onward (provider claim)",
        "bangladesh_coverage": True,
        "precipitation_variables": ["precipitation"],
        "licensing": "CC BY 4.0",
        "reproducibility": "HTTPS historical-forecast-api.open-meteo.com",
        "access_requirements": "none",
        "historical_forecasts_reconstructable": False,
        "existed_during_target_b_period": "partial (2021–2024)",
        "acquired": False,
        "in_spatial_cube": False,
        "availability_in_horizon": UNAVAILABLE,
        "note": "Provider documents a blended product of different runs. Not unblended forecast-vintage.",
        "source_url": "https://open-meteo.com/en/features",
    },
    {
        "id": "open-meteo-single-runs",
        "product_name": "Open-Meteo Single Runs API",
        "provider": "Open-Meteo",
        "forecast_type": KIND_FORECAST,
        "spatial_resolution": "ECMWF IFS HRES ~9 km",
        "temporal_resolution": "hourly, full run",
        "forecast_issue_time": "UTC initialisation via run= (00/06/12/18)",
        "forecast_lead_time": "typically 7–15 days (IFS HRES ~10–15 d)",
        "historical_archive": "ECMWF IFS HRES from 2024-03-14; other models from 2026-04",
        "bangladesh_coverage": True,
        "precipitation_variables": ["precipitation"],
        "licensing": "CC BY 4.0; ECMWF open data terms for IFS",
        "reproducibility": "HTTPS; query by initialisation time",
        "access_requirements": "none for the API; IFS open-data era only",
        "historical_forecasts_reconstructable": True,
        "existed_during_target_b_period": "only evt:2024-06-22 and only after 2024-03-14",
        "acquired": False,
        "in_spatial_cube": False,
        "max_lead_hours": 240,
        "archive_start": "2024-03-14",
        "note": "True vintage for a slice of 2024. Does not cover 2015–2023 events.",
        "source_url": "https://openmeteo.substack.com/p/single-runs-api",
    },
    {
        "id": "tigge-ecmwf-ens",
        "product_name": "TIGGE ECMWF ensemble / high-resolution precipitation",
        "provider": "ECMWF via TIGGE / ECDS",
        "forecast_type": KIND_FORECAST,
        "spatial_resolution": "~0.25–0.5° in TIGGE (centre-dependent)",
        "temporal_resolution": "6-hourly",
        "forecast_issue_time": "00/12 UTC initialisation (and 06/18 for some centres)",
        "forecast_lead_time": "medium-range, typically ~15 days (ECMWF ENS)",
        "historical_archive": "October 2006–present (48 h access delay)",
        "bangladesh_coverage": True,
        "precipitation_variables": ["total precipitation (param 228228)"],
        "licensing": "CC BY 4.0 for ECMWF/NCEP/UKMO/DWD TIGGE; some centres CC BY-NC 4.0",
        "reproducibility": "ECDS / MARS TIGGE; registration required",
        "access_requirements": "ECMWF Data Store account; 48 h delay",
        "historical_forecasts_reconstructable": True,
        "existed_during_target_b_period": True,
        "acquired": False,
        "in_spatial_cube": False,
        "max_lead_hours": 360,
        "archive_start": "2006-10-01",
        "note": "Best candidate for true 2015–2024 vintage. Not downloaded. Do not treat as in-cube.",
        "source_url": "https://ecds.ecmwf.int/datasets/tigge-forecasts",
    },
    {
        "id": "noaa-gefs-v12",
        "product_name": "NOAA GEFSv12 reforecast + operational GEFS",
        "provider": "NOAA / NCEP",
        "forecast_type": KIND_FORECAST,
        "spatial_resolution": "0.25–0.5°",
        "temporal_resolution": "3–6 hourly",
        "forecast_issue_time": "00/06/12/18 UTC",
        "forecast_lead_time": "~16 days operational; reforecast 16 days",
        "historical_archive": "reforecast ~2000–2019 (frozen 2017 model); operational GEFS thereafter",
        "bangladesh_coverage": True,
        "precipitation_variables": ["apcp"],
        "licensing": "US public domain",
        "reproducibility": "NOMADS / AWS / NCEI; large GRIB volumes",
        "access_requirements": "object-store or NCEI; no CDS",
        "historical_forecasts_reconstructable": "reforecasts are not the operational system of the day; operational archive is vintage",
        "existed_during_target_b_period": True,
        "acquired": False,
        "in_spatial_cube": False,
        "max_lead_hours": 384,
        "note": "Reforecasts ≠ 2015–2019 operational vintage. Operational GEFS needed for true 2020–2024 runs.",
        "source_url": "https://www.ncei.noaa.gov/products/weather-climate-models/global-ensemble-forecast",
    },
    {
        "id": "glofas-reanalysis-open-meteo",
        "product_name": "GloFAS v4 river discharge reanalysis (Open-Meteo Flood API)",
        "provider": "Open-Meteo / CEMS GloFAS",
        "forecast_type": KIND_MODELLED,
        "spatial_resolution": "0.05° cell, used as AOI scalar",
        "temporal_resolution": "daily",
        "forecast_issue_time": "none (reanalysis forced by ERA5)",
        "forecast_lead_time": "n/a",
        "historical_archive": "2015-01-01 … 2024-12-31 in discharge_2015_2024.json (3 proxy cities)",
        "bangladesh_coverage": "3 cells only (sunamganj, dhaka, sylhet proxies)",
        "precipitation_variables": [],
        "licensing": "CC BY 4.0; underlying CEMS-FLOODS / Copernicus",
        "reproducibility": "flood-api.open-meteo.com forecast_days=0",
        "access_requirements": "none for the 3-cell snapshot",
        "historical_forecasts_reconstructable": False,
        "existed_during_target_b_period": True,
        "acquired": True,
        "in_spatial_cube": True,
        "availability_pre_t0": OBSERVED_AVAILABLE,
        "availability_in_horizon": POST_T0_OBSERVATION,
        "note": "MODELLED reanalysis. Cube lookback is aligned to valid_at−192 h, not Target B t0.",
        "source_url": "https://flood-api.open-meteo.com/v1/flood",
    },
    {
        "id": "cems-glofas-forecast",
        "product_name": "GloFAS forecast river discharge",
        "provider": "CEMS / Copernicus EWDS cems-glofas-forecast",
        "forecast_type": KIND_FORECAST,
        "spatial_resolution": "0.05°",
        "temporal_resolution": "daily",
        "forecast_issue_time": "00 UTC forecast date",
        "forecast_lead_time": "30 days",
        "historical_archive": "operational archive on EWDS/CDS (credentials)",
        "bangladesh_coverage": True,
        "precipitation_variables": [],
        "licensing": "Copernicus CEMS-FLOODS open (attribution)",
        "reproducibility": "CDS/EWDS API; not the Open-Meteo forecast_days=0 snapshot",
        "access_requirements": "CDS/EWDS account",
        "historical_forecasts_reconstructable": True,
        "existed_during_target_b_period": True,
        "acquired": False,
        "in_spatial_cube": False,
        "max_lead_hours": 720,
        "note": "True hydrological forecast vintage. Not acquired. Do not confuse with GloFAS reanalysis Q.",
        "source_url": "https://ewds.climate.copernicus.eu/datasets/cems-glofas-forecast",
    },
]


def source_by_id(source_id: str) -> dict:
    for row in FORECAST_SOURCES:
        if row["id"] == source_id:
            return row
    raise KeyError(source_id)


def product_year_coverage(source: dict, year: int) -> str:
    start = source.get("archive_start")
    if source["id"] == "era5-land-open-meteo-lattice":
        return "COVERED" if 2016 <= year <= 2024 else "OUTSIDE_ARCHIVE"
    if source["id"] == "open-meteo-previous-runs":
        return "COVERED" if year >= 2024 else "OUTSIDE_ARCHIVE"
    if source["id"] == "open-meteo-single-runs":
        return "COVERED" if year >= 2024 else "OUTSIDE_ARCHIVE"
    if source["id"] == "open-meteo-historical-forecast":
        return "PARTIAL_BLENDED" if year >= 2021 else "OUTSIDE_ARCHIVE"
    if source["id"] == "tigge-ecmwf-ens":
        return "COVERED_NOT_ACQUIRED" if year >= 2007 else "OUTSIDE_ARCHIVE"
    if source["id"] == "noaa-gefs-v12":
        return "COVERED_NOT_ACQUIRED"
    if source["id"] == "glofas-reanalysis-open-meteo":
        return "COVERED" if 2015 <= year <= 2024 else "OUTSIDE_ARCHIVE"
    if source["id"] == "cems-glofas-forecast":
        return "COVERED_NOT_ACQUIRED"
    if start:
        return "COVERED_NOT_ACQUIRED" if year >= int(str(start)[:4]) else "OUTSIDE_ARCHIVE"
    return "UNKNOWN"


def hypothetical_lead_coverage(delta_t_hours: float, max_lead_hours: Optional[float]) -> Optional[float]:
    """Fraction of (t0,t1] a product *could* cover if acquired. Not actual coverage."""
    if not max_lead_hours or delta_t_hours <= 0:
        return None
    return float(min(1.0, float(max_lead_hours) / float(delta_t_hours)))
