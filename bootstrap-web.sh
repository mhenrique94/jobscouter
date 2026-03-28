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

parse_args "${1:-}"

TOTAL_PHASES=3
if [[ "$INSTALL_ONLY" -eq 1 ]]; then
  TOTAL_PHASES=2
fi

phase "1/${TOTAL_PHASES}" "Pre-checagens frontend"
ensure_web_dir
ensure_node_tools

if [[ "$INSTALL_ONLY" -eq 0 ]]; then
  ensure_env_file

  if [[ "$ENV_WAS_CREATED" -eq 1 ]]; then
    echo ""
    echo "[BLOQUEIO] O arquivo .env da raiz foi criado agora e requer revisao manual."
    echo "  - Ajuste as variaveis necessarias e execute novamente: make install-front ou make run-front"
    exit 1
  fi

  load_frontend_env
fi

phase "2/${TOTAL_PHASES}" "Dependencias frontend"
install_dependencies_if_needed

if [[ "$INSTALL_ONLY" -eq 1 ]]; then
  ok "Dependencias do frontend instaladas sem iniciar servidor"
  exit 0
fi

if [[ "$NO_SERVER" -eq 1 ]]; then
  phase "3/3" "Finalizado (--bootstrap-only)"
  ok "Frontend preparado sem iniciar servidor"
  exit 0
fi

phase "3/3" "Iniciando frontend"
cd "$WEB_DIR"
exec npm run dev
