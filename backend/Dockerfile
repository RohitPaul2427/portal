# ── LEAMSS Portal API ──────────────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8001 \
    APP_ROOT=/app \
    UPLOADS_ROOT=/app/uploads \
    WEB_CONCURRENCY=1

# System libraries for WeasyPrint (Cairo, Pango, GDK-Pixbuf) and fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
        libffi8 shared-mime-info fonts-liberation fonts-dejavu-core fontconfig curl \
    && rm -rf /var/lib/apt/lists/*

# Repository layout inside the image mirrors the repo: /app/backend
WORKDIR /app/backend

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as an unprivileged user
RUN useradd --create-home --uid 10001 leamss \
    && mkdir -p /app/uploads /app/backups /app/backend/storage /app/backend/uploads \
    && chown -R leamss:leamss /app
USER leamss

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

# NOTE: background schedulers (digests, scrapers) start inside the app process,
# so keep WEB_CONCURRENCY=1 until the scheduler is moved to its own process.
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY} --proxy-headers --forwarded-allow-ips='*'"]
