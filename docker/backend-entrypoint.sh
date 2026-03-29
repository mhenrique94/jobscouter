#!/usr/bin/env sh
set -eu

# Ensure schema is up to date before starting API.
alembic upgrade head

APP_ENV="${APP_ENV:-development}"
RELOAD_ARG=""

if [ "${UVICORN_RELOAD+x}" = "x" ]; then
	# Only explicit truthy values enable reload; falsy values disable it even in development.
	UVICORN_RELOAD_NORMALIZED="$(printf '%s' "$UVICORN_RELOAD" | tr '[:upper:]' '[:lower:]')"
	case "$UVICORN_RELOAD_NORMALIZED" in
		1|true|yes|on)
			RELOAD_ARG="--reload"
			;;
		0|false|no|off|"")
			RELOAD_ARG=""
			;;
		*)
			echo "  - WARN: UVICORN_RELOAD invalido ('$UVICORN_RELOAD'); usando reload desabilitado" >&2
			RELOAD_ARG=""
			;;
	esac
elif [ "$APP_ENV" != "production" ]; then
	RELOAD_ARG="--reload"
fi

exec uvicorn jobscouter.api.main:app --host 0.0.0.0 --port 8000 $RELOAD_ARG
