# ---- build stage ----
FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml .
COPY app ./app
RUN pip install --no-cache-dir --prefix=/install .

# ---- runtime stage ----
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 devpilot
COPY --from=build /install /usr/local
WORKDIR /app
COPY app ./app
USER devpilot
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD curl -fs http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
