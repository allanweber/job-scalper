# Single image for all Python services (API, admin, worker, scheduler).
# The compose file selects which process each container runs via `command:`.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build deps only for the install step (libsql/cryptography may build); the final
# layer keeps the runtime slim. No PDF/Playwright system libs — the service does
# not render PDFs at runtime (see docs/DESIGN.md).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached until pyproject changes).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[api]"

# A non-root runtime user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080 8081

# Default to the public API; compose overrides `command` per service.
CMD ["uvicorn", "--factory", "scalper.service.app:create_app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
