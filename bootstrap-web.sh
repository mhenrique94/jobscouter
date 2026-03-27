#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="${PROJECT_ROOT}/web"
LOCK_FILE="${WEB_DIR}/package-lock.json"
HASH_MARKER="${WEB_DIR}/.package-lock.hash"
ENV_FILE="${PROJECT_ROOT}/.env"
ENV_EXAMPLE_FILE="${PROJECT_ROOT}/.env.example"
ENV_WAS_CREATED=0

NO_SERVER=0
if [[ "${1:-}" == "--bootstrap-only" ]]; then
  NO_SERVER=1
fi

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

ensure_web_dir() {
  [[ -d "$WEB_DIR" ]] || fail "Pasta web nao encontrada em ${WEB_DIR}"
  ok "Pasta web encontrada"
}

ensure_node_tools() {
  command -v node >/dev/null 2>&1 || fail "node nao encontrado"
  command -v npm >/dev/null 2>&1 || fail "npm nao encontrado"
  ok "Node e npm detectados"
}

ensure_env_file() {
  if [[ -f "$ENV_FILE" ]]; then
    ok ".env da raiz encontrado"
    return
  fi

  if [[ -f "$ENV_EXAMPLE_FILE" ]]; then
    cp "$ENV_EXAMPLE_FILE" "$ENV_FILE"
    ENV_WAS_CREATED=1
    ok "Criado .env da raiz a partir de .env.example"
    return
  fi

  fail "Nao encontrei .env nem .env.example na raiz"
}

load_frontend_env() {
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a

  export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8000}"
  export NEXT_PUBLIC_API_BASE_PATH="${NEXT_PUBLIC_API_BASE_PATH:-}"
  ok "Variaveis do frontend carregadas via .env da raiz"
}

install_dependencies_if_needed() {
  [[ -f "$LOCK_FILE" ]] || fail "package-lock.json nao encontrado em web"

  local current_hash
  local saved_hash=""

  current_hash="$(compute_hash "$LOCK_FILE")"
  if [[ -f "$HASH_MARKER" ]]; then
    saved_hash="$(cat "$HASH_MARKER")"
  fi

  cd "$WEB_DIR"

  if [[ "$current_hash" == "$saved_hash" && -d "node_modules" ]]; then
    ok "Dependencias do frontend em cache (package-lock sem alteracao)"
    return
  fi

  if [[ ! -d "node_modules" ]]; then
    ok "Primeira execucao do frontend; instalando dependencias"
  else
    ok "package-lock alterado; atualizando dependencias"
  fi

  npm install
  echo "$current_hash" > "$HASH_MARKER"
  ok "Dependencias do frontend instaladas/atualizadas"
}

phase "1/3" "Pre-checagens frontend"
ensure_web_dir
ensure_node_tools
ensure_env_file

if [[ "$ENV_WAS_CREATED" -eq 1 ]]; then
  echo ""
  echo "[BLOQUEIO] O arquivo .env da raiz foi criado agora e requer revisao manual."
  echo "  - Ajuste as variaveis necessarias e execute novamente: ./bootstrap-web.sh ou make web"
  exit 1
fi

load_frontend_env

phase "2/3" "Dependencias frontend"
install_dependencies_if_needed

if [[ "$NO_SERVER" -eq 1 ]]; then
  phase "3/3" "Finalizado (--bootstrap-only)"
  ok "Frontend preparado sem iniciar servidor"
  exit 0
fi

phase "3/3" "Iniciando frontend"
cd "$WEB_DIR"
exec npm run dev
