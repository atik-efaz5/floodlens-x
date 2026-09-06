# PHASE 7.7 — Alerts + Saved Locations + Reports + Sharing

**Date:** 2026-09-03  
**Scope:** Persistent saved locations, metric-gated in-app alerts with a deterministic state machine, immutable report snapshots (JSON/CSV/PDF), and shareable analysis links that never substitute live values.  
**Not in scope:** email/push delivery, official evacuation orders, fabricated metrics, solver changes, model training, spatial AI enablement.

Scientific freeze (unchanged):

| Item | Status |
|---|---|
| Spatial AI | NOT_VALIDATED |
| Spatial API | UNAVAILABLE |
| Target B | PARTIALLY FEASIBLE |
| Model training | NOT AUTHORIZED |
| Solver (`src/floodlens/numerical/**`) | unmodified |

---

## 1. Saved locations

Users persist personal monitoring places via `POST /api/v1/locations` (and the legacy `POST /api/v1/places` wrapper).

Stored fields: `id` (location_id), `name`, `location_type`, coordinates (`latitude`/`longitude`), `city_id`, optional `river_id`, `zoom`, `layers`, `alert_configuration`, `created_at`, `updated_at`, `owner`.

Location types: `city`, `district`, `region`, `river`, `research_area`, `emergency_area`, `coordinate`.

Owner identity is taken from the demo bearer token (`demo.<role>`). Client `user_id` is ignored.

Queries are owner-scoped and capped at 50 rows. There is no global dump of every saved location.

## 2. Alerts

`POST /api/v1/alerts` creates a personal / operational / experiment / system alert.

Supported metrics (legitimate products exist):

- `flood_probability` (heuristic DEMO, not calibrated)
- `risk_score`
- `risk_level`
- `forecast_confidence` (heuristic, NOT_CALIBRATED)
- `rainfall_mm` only when precipitation observations are ingested

Rejected as **METRIC UNAVAILABLE** (creation fails; no silent broken alert):

- `river_level` / `water_level`
- `discharge`
- `flood_depth`
- `population`
- `infrastructure_exposure`

Operators: `gt`, `gte`, `lt`, `lte`, `eq`. NaN, infinity, and malformed thresholds are rejected. Probability/score thresholds must be in `[0, 1]`.

Channel implemented: **in-app**. Email and push are prepared in the catalog and rejected at creation until implemented.

Safety copy: threshold notices such as “exceeded your configured threshold.” Alerts are not flood declarations and not official evacuation orders.

## 3. Alert state machine

```
ARMED
  → condition CURRENTLY_TRUE → TRIGGERED (one notification event)
  → user acknowledge → ACKNOWLEDGED
  → condition CURRENTLY_FALSE → RESET → ARMED
```

Evaluation statuses: `CURRENTLY_TRUE`, `CURRENTLY_FALSE`, `UNAVAILABLE`, `STALE`, `ERROR`.

**UNAVAILABLE is never classified as FALSE** and does not trigger. STALE true-matches are labeled STALE and do not fire a new trigger from ARMED.

`GET /api/v1/alerts/evaluate` returns `fired` only for newly `ARMED→TRIGGERED` transitions. Already triggered alerts are not re-appended (deduplication).

## 4. Notifications

In-app only. History: `GET /api/v1/alerts/{id}/history` with trigger time, metric, threshold, actual value (or **UNAVAILABLE**), source, status, acknowledged flag.

Acknowledge: `POST /api/v1/alerts/{id}/acknowledge`.

Email/push: architecture only. The API and UI state that they are **not delivered**.

## 5. Reports

`POST /api/v1/reports` builds an immutable snapshot from verified products:

- region (heuristic risk + forecast + impact)
- scenario (baseline, modified parameters, results, difference, impact)
- historical (`event_id`) via the Phase 7.6 historical report

Sections are populated from real products. Missing layers stay omitted or explicitly `UNAVAILABLE` — never filled with invented numbers.

Population exposure remains null. River water level and discharge remain UNAVAILABLE. `river_level_applied_to_solver` remains **false / STORED ONLY / NOT APPLIED**. Spatial AI remains absent (`ai_flood_model: null`).

Historical reports with no compatible prediction artifact: `FORECAST VS REALITY: UNAVAILABLE` (`forecast_accuracy_omitted`).

The assistant tools `generate_report` and `share_analysis` call the same backend; they do not invent numbers.

## 6. Snapshot semantics

A report is a **SNAPSHOT**. Stored fields include `report_id`, `created_at`/`generated_at`, `created_by`, `snapshot_time`, `content_version`, `source_versions`, `model_versions`, `scenario_id`, `job_id`, `live=false`, `immutable=true`.

`GET /api/v1/reports/{id}` returns the stored object. It is not recomputed against current live data.

Share records freeze a JSON copy of the report at share time. Mutating the live report record later does not rewrite the share snapshot.

## 7. PDF / CSV / JSON

- **JSON:** raw verified values, nulls, status, units, provenance.
- **CSV:** `field,value,status`. Null/unavailable fields are empty with status `UNAVAILABLE`. Null is never written as `0`.
- **PDF:** title, `SNAPSHOT GENERATED AT: [timestamp]`, location, summary, metrics, map state, evidence/limitations/provenance. Scenario PDFs include `river_level_applied_to_solver: STORED ONLY / NOT APPLIED`. Historical PDFs include `FORECAST VS REALITY: UNAVAILABLE` when omitted.

Exports are rate-limited.

## 8. Sharing

`POST /api/v1/shares/{report_id}?visibility=private|organization|public` creates a stable share id.

Default visibility is **private**. Public/link access is opt-in. Organization shares require sign-in.

Shared payload preserves location, scenario, timestamp, model/method, results, map state, layers, assumptions, and provenance. Banner:

`Analysis generated at TIMESTAMP. Using: MODEL. Dataset: VERSION. This is a historical snapshot.`

`GET /api/v1/shares/{share_id}` returns the frozen snapshot with `live=false`. Current live values are not substituted.

## 9. Stale-share behavior

Every successful open includes:

- status `SHARED SNAPSHOT`
- generation timestamp, model, dataset
- `stale_notice`: current live data may differ; the historical snapshot is not rewritten

Revoked or unauthorized access: HTTP 404 `SHARE_UNAVAILABLE`. The underlying report is not deleted.

## 10. Authorization

| Role | Saved locations | Alerts | Reports / shares |
|---|---|---|---|
| GENERAL | personal | personal | personal snapshots |
| EMERGENCY | personal | personal + operational | operational snapshots |
| RESEARCHER | personal / experiment | personal + experiment | experiment snapshots |
| ADMIN | all | including system | all |

General users cannot create `system` (admin) alerts. Researcher cannot create system alerts.

## 11. Security

- Owner identity is derived from the Authorization header. Client `user_id` is ignored.
- Location, alert, report, and revoke operations are owner-checked server-side.
- Private shares require the owner. Public shares are explicit.
- Rate limits (in-process): alert create 40, report generate 30, share create 30, export 40, location create 50 per identity.

This remains a demo IdP (`demo.<role>`), not production OIDC.

## 12. Provenance

Reports and shares retain source, timestamps, dataset version, model version, processing/`content_version`, scenario ID, and job ID where applicable.

Freshness labels: `REAL`, `STALE`, `DEMO`, `SIMULATED`, `UNAVAILABLE`. Heuristic products are DEMO. **LIVE is never claimed** for simulated/heuristic products.

Map snapshots store the actual analysis map state (center, zoom, layers, river, scenario, timestamp) rather than a generic unrelated map.

## 13. Testing

`tests/test_phase77_alerts_reports_sharing.py` covers:

- locations: create, rename, delete, restore context (not stale results), authorization, ignored client user_id
- alerts: creation, validation, supported vs unavailable metrics, NaN/inf, role kinds, channels
- evaluation: state transitions, deduplication, history, UNAVAILABLE ≠ FALSE
- reports: snapshot flags, null population, unavailable river level, scenario river-level not applied, historical forecast omission, PDF/CSV/JSON
- sharing: create, private/public access, revoke, frozen snapshot vs mutated live record, provenance
- assistant generate_report / share_analysis
- spatial AI remains NOT_VALIDATED
- frontend copy for METRIC UNAVAILABLE, snapshot banners, confirmation dialogs

## 14. Browser / E2E

Manual/browser checks (Command Center at the Vite origin, API on `:8000`):

1. Search Dhaka → Save location → My Locations → Reopen Dhaka (map context only).
2. Create flood-probability alert → save → view state/history.
3. Attempt water-level alert → METRIC UNAVAILABLE; save disabled.
4. Run +30% rainfall scenario → generate report → snapshot banner, `live=false`.
5. Share report → open share → timestamp / model / dataset / historical snapshot.
6. Revoke share → SHARE UNAVAILABLE.

## 15. Limitations

- Heuristic flood probability and risk are DEMO / NOT_CALIBRATED.
- No ingested gauge water level, discharge, flood depth, or population grid.
- Email and push are not delivered.
- In-memory store; production target remains PostgreSQL/PostGIS.
- Rate limits are process-local, not distributed.
- Map snapshot is serialized state (center/zoom/layers), not a rendered PNG.
- Demo role switcher is not a production identity provider.

## 16. Future notification channels

Prepared but not implemented:

- **email** — would require verified addresses, templates that keep threshold language (not flood declarations), and delivery audit.
- **push** — would require device tokens and the same state machine / dedup rules.

Until those exist, creation with `channel=email` or `channel=push` is rejected with `CHANNEL_NOT_IMPLEMENTED`.
