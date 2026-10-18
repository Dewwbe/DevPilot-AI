# Throwaway sandbox image for the check runner (ruff, pytest, pip-audit, eslint via npm).
# Started per check by the check-worker, run non-root with a read-only root filesystem.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir ruff pip-audit pytest \
    && useradd --create-home --uid 10002 runner

USER runner
WORKDIR /tmp
