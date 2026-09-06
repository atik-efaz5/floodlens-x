"""Optional Celery entrypoint. Phase 3 uses FastAPI BackgroundTasks + in-process jobs.

Celery/Redis are not required. When Celery is installed it still executes
enqueue_job in-process unless a broker is later configured.
"""

from __future__ import annotations


def enqueue_or_celery(kind: str, city_id: str, payload: dict) -> dict:
    try:
        from celery import Celery  # type: ignore
    except ImportError:
        from floodlens.application.jobs import enqueue_job

        job = enqueue_job(kind, city_id, payload)
        job["queue"] = "in-process"
        return job

    # Celery is present: still execute in-process unless a broker is configured.
    from floodlens.application.jobs import enqueue_job

    job = enqueue_job(kind, city_id, payload)
    job["queue"] = "in-process"
    job["celery_available"] = True
    return job


def celery_app():
    try:
        from celery import Celery
    except ImportError:
        return None
    app = Celery("floodlens", broker="redis://127.0.0.1:6379/0")
    return app
