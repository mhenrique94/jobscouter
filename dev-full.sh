#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID=""

cleanup() {
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    echo ""
    echo "[cleanup] Encerrando backend (PID $BACKEND_PID)"
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

echo "[1/4] Preparando backend"
"${PROJECT_ROOT}/bootstrap.sh" --bootstrap-only

echo "[2/4] Iniciando backend em background"
"${PROJECT_ROOT}/.venv/bin/python" -m uvicorn jobscouter.api.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "  - Backend PID: ${BACKEND_PID}"

echo "[3/4] Preparando frontend"
"${PROJECT_ROOT}/bootstrap-web.sh" --bootstrap-only

echo "[4/4] Iniciando frontend (foreground)"
cd "${PROJECT_ROOT}"
exec "${PROJECT_ROOT}/bootstrap-web.sh"
