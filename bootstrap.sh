#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
HASH_MARKER="${VENV_DIR}/.pyproject.hash"
ENV_FILE="${PROJECT_ROOT}/.env"
ENV_EXAMPLE_FILE="${PROJECT_ROOT}/.env.example"
ENV_WAS_CREATED=0

NO_SERVER=0
INSTALL_ONLY=0

phase() {
  echo ""
  echo "[$1] $2"
}

ok() {
  echo "  - $1"
}

fail() {
  echo "  - ERRO: $1" >&2
  exit 1
}

parse_args() {
  case "${1:-}" in
    "") ;;
    --bootstrap-only)
      NO_SERVER=1
      ;;
    --install-only)
      NO_SERVER=1
      INSTALL_ONLY=1
      ;;
    *)
      fail "Parametro invalido: ${1}. Use --bootstrap-only ou --install-only"
      ;;
  esac
}

compute_hash() {
  local file_path="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file_path" | awk '{print $1}'
  elif command -v md5sum >/dev/null 2>&1; then
    md5sum "$file_path" | awk '{print $1}'
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$file_path" | awk '{print $NF}'
  else
    cksum "$file_path" | awk '{print $1}'
  fi
}

ensure_python() {
  command -v python3 >/dev/null 2>&1 || fail "python3 nao encontrado"
  python3 - <<'PY' || exit 1
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ e obrigatorio")
PY
  ok "Python 3.11+ detectado"
}

resolve_compose_cmd() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
  else
    fail "Docker Compose nao encontrado (docker compose ou docker-compose)"
  fi
  ok "Docker Compose detectado"
}

ensure_env_file() {
  if [[ -f "$ENV_FILE" ]]; then
    ok ".env ja existe"
    return
  fi

  if [[ -f "$ENV_EXAMPLE_FILE" ]]; then
    cp "$ENV_EXAMPLE_FILE" "$ENV_FILE"
    ENV_WAS_CREATED=1
    ok "Criado .env a partir de .env.example"
    return
  fi

  fail "Nao encontrei .env nem .env.example"
}

ensure_venv() {
  if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
    ok "Virtualenv criado"
  else
    ok "Virtualenv ja existe"
  fi
}

install_dependencies_if_needed() {
  local current_hash
  local saved_hash=""

  current_hash="$(compute_hash "${PROJECT_ROOT}/pyproject.toml")"
  if [[ -f "$HASH_MARKER" ]]; then
    saved_hash="$(cat "$HASH_MARKER")"
  fi

  if [[ "$current_hash" == "$saved_hash" ]]; then
    if "$VENV_PYTHON" -c "import fastapi, sqlmodel, alembic" >/dev/null 2>&1; then
      ok "Dependencias em cache (pyproject sem alteracao)"
      return
    fi
    ok "Hash igual, mas pacotes ausentes; reinstalando"
  else
    ok "Primeira execucao ou pyproject alterado; instalando dependencias"
  fi

  "$VENV_PYTHON" -m pip install --upgrade pip >/dev/null
  "$VENV_PYTHON" -m pip install -e "${PROJECT_ROOT}[dev]"
  echo "$current_hash" > "$HASH_MARKER"
  ok "Dependencias instaladas/atualizadas"
}

wait_for_postgres() {
  local max_attempts=30
  local attempt=1
  local postgres_user="${POSTGRES_USER:-postgres}"

  while [[ "$attempt" -le "$max_attempts" ]]; do
    if "${COMPOSE_CMD[@]}" exec -T db pg_isready -U "$postgres_user" >/dev/null 2>&1; then
      ok "PostgreSQL pronto"
      return
    fi
    echo "  - aguardando PostgreSQL (${attempt}/${max_attempts})"
    attempt=$((attempt + 1))
    sleep 1
  done

  fail "PostgreSQL nao ficou pronto a tempo"
}

parse_args "${1:-}"

TOTAL_PHASES=7
if [[ "$INSTALL_ONLY" -eq 1 ]]; then
  TOTAL_PHASES=4
fi

phase "1/${TOTAL_PHASES}" "Pre-checagens"
ensure_python
if [[ "$INSTALL_ONLY" -eq 0 ]]; then
  resolve_compose_cmd
fi

phase "2/${TOTAL_PHASES}" "Arquivo de ambiente"
ensure_env_file

if [[ "$ENV_WAS_CREATED" -eq 1 ]]; then
  echo ""
  echo "[BLOQUEIO] O arquivo .env foi criado agora e requer revisao manual."
  echo "  - Preencha credenciais/chaves (ex.: GEMINI_API_KEY) e caminhos necessarios."
  echo "  - Depois execute novamente: make install ou make run-back"
  exit 1
fi

phase "3/${TOTAL_PHASES}" "Ambiente Python"
ensure_venv
install_dependencies_if_needed

if [[ "$INSTALL_ONLY" -eq 1 ]]; then
  phase "4/4" "Finalizado (--install-only)"
  ok "Dependencias do backend instaladas sem subir banco/API"
  exit 0
fi

phase "4/7" "Banco de dados (Docker)"
"${COMPOSE_CMD[@]}" up -d db >/dev/null
ok "Container db (PostgreSQL) iniciado"
wait_for_postgres

phase "5/7" "Migracoes"
cd "$PROJECT_ROOT"
"$VENV_PYTHON" -m alembic upgrade head
ok "Migracoes aplicadas"

phase "6/7" "Resumo"
echo "  - API: http://127.0.0.1:8000"
echo "  - Docs: http://127.0.0.1:8000/docs"
echo "  - Banco: postgres://postgres:postgres@localhost:5432/jobscouter"

if [[ "$NO_SERVER" -eq 1 ]]; then
  phase "7/7" "Finalizado (--bootstrap-only)"
  ok "Bootstrap concluido sem subir servidor"
  exit 0
fi

phase "7/7" "Iniciando API"
exec "$VENV_PYTHON" -m uvicorn jobscouter.api.main:app --host 0.0.0.0 --port 8000
