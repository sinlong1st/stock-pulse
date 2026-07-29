# StockPulse — single always-on process (scheduler + Telegram listener + web).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the package + its dependencies. README is referenced by pyproject.
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install .

# Alembic lives at the repo root and runs at container start (see entrypoint).
COPY alembic ./alembic
COPY alembic.ini ./
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Persistent state (SQLite + rolling theme memory) lives here; mount a volume.
RUN mkdir -p /app/data
EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
