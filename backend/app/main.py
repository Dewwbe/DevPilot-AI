from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, diagnoses, health, repositories, stats, webhooks
from app.core import metrics
from app.core.db import init_db
from app.core.logging import configure_logging
from app.services.auth import require_user


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
app.include_router(auth.router)  # public: sign-in endpoints
app.include_router(webhooks.router)  # public: authenticated by its HMAC signature instead
# Everything below needs a signed-in user (a no-op while OAuth is not configured, i.e. local dev).
protected = [Depends(require_user)]
app.include_router(repositories.router, dependencies=protected)
app.include_router(diagnoses.router, dependencies=protected)
app.include_router(stats.router, dependencies=protected)


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    """Scraped by Prometheus inside the cluster; the ingress does not route this path."""
    body, content_type = metrics.render()
    return Response(body, media_type=content_type)
