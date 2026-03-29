#!/usr/bin/env sh
set -eu

# Ensure schema is up to date before starting API.
alembic upgrade head

exec uvicorn jobscouter.api.main:app --host 0.0.0.0 --port 8000
