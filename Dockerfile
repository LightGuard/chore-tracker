# syntax=docker/dockerfile:1.7

# Build the Python virtual environment from the committed lock file so image
# dependencies are exactly the versions used by the application's quality gates.
FROM python:3.15.2-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.15.2-slim AS runtime

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app /data \
    && chown -R app:app /app /data

WORKDIR /app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder --chown=app:app /app/.venv /app/.venv
# The project is installed in editable mode by uv; keep the source available.
COPY --chown=app:app src ./src
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations

USER app

# SQLite lives on a mounted volume; the image never contains application data.
VOLUME ["/data"]

EXPOSE 8000

# Image-level health is process liveness. Compose overrides this with the
# readiness endpoint so dependent services wait for migrations and SQLite.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"]

# One process owns the durable weekly rollover, so do not add multiple workers.
CMD ["uvicorn", "chore_tracker.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
