#!/usr/bin/env sh
set -eu

# Ensure schema is up to date before starting API.
alembic upgrade head

APP_ENV="${APP_ENV:-development}"
RELOAD_ARG=""

if [ -n "${UVICORN_RELOAD:-}" ]; then
	RELOAD_ARG="--reload"
elif [ "$APP_ENV" != "production" ]; then
	RELOAD_ARG="--reload"
fi

exec uvicorn jobscouter.api.main:app --host 0.0.0.0 --port 8000 $RELOAD_ARG
