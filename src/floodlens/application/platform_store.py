"""In-memory platform store matching db/schema.sql.

PostgreSQL/PostGIS is the production target; this store keeps tests and local
dev working without a database. Swap behind the same methods later.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from floodlens.application.provenance import isoformat, utcnow


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class PlatformStore:
    organizations: Dict[str, dict] = field(default_factory=dict)
    users: Dict[str, dict] = field(default_factory=dict)
    places: Dict[str, dict] = field(default_factory=dict)
    rivers: Dict[str, dict] = field(default_factory=dict)
    river_segments: Dict[str, dict] = field(default_factory=dict)
    assets: Dict[str, dict] = field(default_factory=dict)
    observations: List[dict] = field(default_factory=list)
    jobs: Dict[str, dict] = field(default_factory=dict)
    artifacts: Dict[str, dict] = field(default_factory=dict)
    alerts: Dict[str, dict] = field(default_factory=dict)
    alert_events: List[dict] = field(default_factory=list)
    reports: Dict[str, dict] = field(default_factory=dict)
    shares: Dict[str, dict] = field(default_factory=dict)
    audit_logs: List[dict] = field(default_factory=list)
    ingest_runs: List[dict] = field(default_factory=list)
    rate_counts: Dict[str, int] = field(default_factory=dict)
    experiments: Dict[str, dict] = field(default_factory=dict)

    def reset(self) -> None:
        self.__init__()

    def put_asset(self, asset: dict) -> dict:
        asset = dict(asset)
        asset.setdefault("id", _id("asset"))
        self.assets[asset["id"]] = asset
        return asset

    def assets_for_city(self, city_id: str, asset_type: Optional[str] = None) -> List[dict]:
        rows = [a for a in self.assets.values() if a["city_id"] == city_id]
        if asset_type:
            rows = [a for a in rows if a["asset_type"] == asset_type]
        return rows

    def put_observation(self, observation: dict) -> dict:
        observation = dict(observation)
        observation.setdefault("id", _id("obs"))
        self.observations.append(observation)
        return observation

    def observations_for(self, variable: str, city_id: Optional[str] = None) -> List[dict]:
        rows = [o for o in self.observations if o["variable"] == variable]
        if city_id:
            rows = [o for o in rows if o.get("city_id") == city_id]
        return sorted(rows, key=lambda row: row["observed_at"])

    def put_job(self, job: dict) -> dict:
        job = dict(job)
        job.setdefault("id", _id("job"))
        job.setdefault("created_at", isoformat())
        job.setdefault("status", "queued")
        self.jobs[job["id"]] = job
        return job

    def get_job(self, job_id: str) -> dict:
        if job_id not in self.jobs:
            raise KeyError(job_id)
        return self.jobs[job_id]

    def put_alert(self, alert: dict) -> dict:
        alert = dict(alert)
        now = isoformat()
        alert.setdefault("id", _id("alert"))
        alert.setdefault("active", True)
        alert.setdefault("state", "ARMED")
        alert.setdefault("created_at", now)
        alert["updated_at"] = now
        self.alerts[alert["id"]] = alert
        return alert

    def put_alert_event(self, event: dict) -> dict:
        event = dict(event)
        event.setdefault("id", _id("alertevt"))
        event.setdefault("at", isoformat())
        self.alert_events.append(event)
        return event

    def put_place(self, place: dict) -> dict:
        place = dict(place)
        now = isoformat()
        place.setdefault("id", _id("place"))
        place.setdefault("created_at", now)
        place["updated_at"] = now
        self.places[place["id"]] = place
        return place

    def put_report(self, report: dict) -> dict:
        report = dict(report)
        now = isoformat()
        report.setdefault("id", _id("report"))
        report.setdefault("generated_at", now)
        report.setdefault("snapshot_time", report["generated_at"])
        report.setdefault("immutable", True)
        report.setdefault("content_version", "platform-v1")
        self.reports[report["id"]] = report
        return report

    def put_share(self, share: dict) -> dict:
        share = dict(share)
        now = isoformat()
        share.setdefault("id", _id("share"))
        share.setdefault("generated_at", now)
        share.setdefault("revoked_at", None)
        share.setdefault("visibility", "private")
        self.shares[share["id"]] = share
        return share

    def put_experiment(self, experiment: dict) -> dict:
        experiment = dict(experiment)
        now = isoformat()
        experiment.setdefault("id", _id("exp"))
        experiment.setdefault("experiment_id", experiment["id"])
        experiment.setdefault("created_at", now)
        experiment["updated_at"] = now
        self.experiments[experiment["id"]] = experiment
        return experiment

    def audit(self, action: str, actor: Optional[str] = None, detail: Optional[dict] = None) -> None:
        self.audit_logs.append(
            {
                "id": _id("audit"),
                "at": isoformat(),
                "actor": actor,
                "action": action,
                "detail": detail or {},
            }
        )


_STORE = PlatformStore()


def get_platform_store() -> PlatformStore:
    return _STORE


def reset_platform_store() -> None:
    _STORE.reset()
