# Scenarios

A scenario is a physics job with a rainfall multiplier and an optional
`river_level_delta_m` (stored on the `ScenarioRecord`; **not** applied as SWE
forcing because there is no river–flood coupling in the baseline).

## API

- `POST /api/v1/scenarios` `{rainfall_multiplier, river_level_delta_m}` enqueues
  a `BackgroundTasks` job. Rainfall comes from `RainfallService` at the 24 h
  horizon unless `rainfall_rate` is supplied.
- `POST /api/v1/scenarios/compare` `{job_ids}` returns per-job max depth,
  flooded area, risk, artifact refs, and a pairwise **difference**. Population
  difference is always `null`.
- Legacy `POST /api/v1/jobs` with `kind=simulation` still runs synchronously
  for existing clients/tests.

## Dhaka demo

1. Ingest OSM + rainfall
2. Physics forecast job (`POST /api/v1/forecast/physics`)
3. Scenario `rainfall_multiplier=1.3`
4. Compare baseline vs scenario

Numbers come from the pipeline, not hardcoded copy.

## Historical events

`HistoricalEvent` is a **contract only** (`GET /api/v1/historical-events`
returns an empty UNAVAILABLE list). No catalog is ingested.
