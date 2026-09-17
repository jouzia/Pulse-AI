FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

# Runs as a non-root user rather than the container default (root) --
# cheap hardening with no local-dev downside (Phase 6 audit finding).
# Created after `pip install` so the install itself, which needs to
# write to system site-packages, still runs as root; only the actual
# running process drops privilege.
RUN useradd --create-home --shell /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
