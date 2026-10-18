from celery import Celery

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
