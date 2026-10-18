from celery import Celery
from celery.signals import worker_ready

from app.core.config import get_settings

s = get_settings()
celery_app = Celery("devpilot", broker=s.redis_url, backend=s.redis_url,
                    include=["app.workers.tasks"])
celery_app.conf.update(
    task_acks_late=True,
    task_time_limit=600,          # hard kill long analyses
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    task_always_eager=s.env == "test",
    # Sandbox checks need the docker socket, so they run on a dedicated, isolated worker.
    task_routes={"run_checks": {"queue": "checks"}},
)


@worker_ready.connect
def _expose_metrics(**_kwargs) -> None:
    """Prometheus endpoint for the worker process. Requires `-P threads` (see compose/chart)."""
    if s.env != "test":
        from app.core import metrics

        metrics.start_worker_server()
