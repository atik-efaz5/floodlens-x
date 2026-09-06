# FLOODLENS-X data layer (Phase 2)

The product UI stays FastAPI + Vite/Leaflet. The numerical solver is unchanged.
This document describes the data foundation: adapters → canonical records →
repository → API envelopes.

## Runtime store

- **`DATABASE_URL` unset (default):** `InMemoryRepository` wrapping the Phase-1
  dict store. Unit tests and local UI work without Postgres.
- **`DATABASE_URL` set:** `PostGISRepository` writes parameterized SQL to the
  tables in `db/schema.sql` plus `db/migrations/002_phase2.sql`, and mirrors
  into memory so list APIs keep working. APIs never execute SQL themselves.
- Docker Compose mounts both SQL files into PostGIS init (`01-schema.sql`,
  `02-phase2.sql`).

Rollback: unset `DATABASE_URL`. Phase-1 tables are not dropped.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | unset (in-memory) | Optional PostGIS connection |
| `FLOODLENS_DEM_PATH` | unset | GeoTIFF on disk; metadata only, no raster bytes in Postgres |
| `OVERPASS_URL` | `https://overpass-api.de/api/interpreter` | OSM Overpass endpoint |
| CORS origins | localhost:5173/5175, `https://floodlens-x.vercel.app` | Frontend origins; extra via `FLOODLENS_CORS_ORIGINS` |

No secrets belong in git. The Vite dev server proxies `/api` to port 8000, so
the browser often never needs CORS; the middleware is for direct API calls
from that origin.

## Provenance

Every collection is wrapped as `{ data|features, provenance, fallback_used }`.

`data_status` is one of `REAL`, `SIMULATED`, `DEMO`, `STALE`, `UNAVAILABLE`,
`PARTIAL`. **`LIVE` is not a permitted status.** Simulated/demo products must
not claim live freshness.

Freshness windows (source-specific): `RECENT`, `STALE`, `EXPIRED`,
`UNAVAILABLE`, `SNAPSHOT` (OSM), `STATIC` (DEM).

Open-Meteo failure is **explicit**: `fallback_used: true` and `data_status:
DEMO`. There is no silent REAL→DEMO swap.

## Providers

1. **OSM** — Overpass for the city bbox (highways, bridges, hospitals, schools,
   clinics, fire/ambulance, shelters). Names are never invented (`name` may be
   null). Dedup by OSM id. If Overpass fails or is rate-limited, the bundled
   Dhaka-style fixture is used with `data_status=DEMO`.
2. **DEM** — If `FLOODLENS_DEM_PATH` exists and rasterio is installed,
   `DEMManager.windowed_stats` reads a 64×64 window. Catalog is `REAL` /
   `STATIC`. Missing path → `UNAVAILABLE` (no fake elevations). Solver jobs
   still use a synthetic DEM labeled `SIMULATED`.
3. **Rainfall** — Open-Meteo hourly series split into `OBSERVED` (past) and
   `FORECAST` (future). HTTP failure → DEMO series + `fallback_used`.
4. **River gauges** — OSM waterway geometry may be a REAL snapshot. Gauge
   `water_level_m` / `discharge_m3s` default to null / `UNAVAILABLE`.
5. **Forecast** — `HeuristicForecastProvider` (labeled `HEURISTIC`). Physics and
   AI providers return `UNAVAILABLE`. `expected_depth` is null until computed.
   `confidence` is a heuristic score (`confidence_kind: heuristic`).
6. **Simulation engine** — in-process `JobService`. Celery is optional: if Redis
   is not up, jobs stay in-process (`celery_app.py`). Full queue migration is
   not required for Phase 2.

## API (additive)

Existing `/api/v1` and `/api/*` routes remain. New/adjusted:

- `GET /api/v1/data-sources`
- `GET /api/v1/infrastructure?bbox=&type=&limit=&offset=` (GeoJSON, cap 500)
- `GET /api/v1/infrastructure/{id}`
- `GET /api/v1/rivers` and `GET /api/v1/rivers/{id}`
- `GET /api/v1/observations?variable=&kind=&from=&to=`
- `GET /api/v1/terrain?city_id=`
- `GET /api/v1/regions`
- `POST /api/v1/ingest/osm` — Overpass then labeled fixture fallback

Overpass and rainfall ingest use an in-process token bucket.

## Jobs and impact

Job JSON is a summary (`artifact_uri`, max depth, flood fraction). Depth arrays
stay in the artifact store, not the job payload. Scenarios persist as
`ScenarioRecord` (`CREATE` → `RUN` → `STORE`).

Impact: point assets use cell depth. Line (road) flood fraction requires
shapely; otherwise `roads_affected.computed=false` with `NOT_COMPUTED`.
`accessibility` is `NOT_COMPUTED`. `population_exposed` is always null.

## Tests

Default pytest is green **without** Postgres. Mark `@pytest.mark.postgis` for
optional Docker tests when `DATABASE_URL` is set. Solver tests must stay green;
do not patch `src/floodlens/numerical`.
