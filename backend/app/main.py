from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import diagnoses, health, repositories, webhooks
from app.core import metrics
from app.core.db import init_db
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    init_db()  # runs Alembic migrations unless DEVPILOT_AUTO_MIGRATE=false (Helm migration Job)
    yield


app = FastAPI(title="DevPilot AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.middleware("http")(metrics.http_metrics_middleware)
app.include_router(health.router)
app.include_router(repositories.router)
app.include_router(diagnoses.router)
app.include_router(webhooks.router)


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    """Scraped by Prometheus inside the cluster; the ingress does not route this path."""
    body, content_type = metrics.render()
    return Response(body, media_type=content_type)
