# Single image for all Python services (API, admin, worker, scheduler).
# The compose file selects which process each container runs via `command:`.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl for healthchecks. psycopg[binary] and cryptography ship wheels, so no
# build toolchain is needed. No PDF/Playwright system libs either — the service
# does not render PDFs at runtime (see docs/DESIGN.md).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached until pyproject changes).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[api]"

# A non-root runtime user that owns the workdir (so any incidental writes work).
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8080 8081

# Default to the public API; compose overrides `command` per service.
CMD ["uvicorn", "--factory", "scalper.service.app:create_app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
