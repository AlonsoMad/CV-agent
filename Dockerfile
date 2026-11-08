# syntax=docker/dockerfile:1

# ---- builder: resolve + compile wheels, never shipped ----
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip wheel --wheel-dir /wheels .

# ---- runtime: only the venv + app metadata ----
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    DEPLOYMENT_NAME=cv-agent

WORKDIR /app

RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels \
    python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --no-compile --no-index --find-links=/wheels cv-agent

CMD ["python", "-m", "worker.entrypoints.worker"]
