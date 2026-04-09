# AGENTS.md — JobScouter

## Visão Geral

**JobScouter** é um sistema completo de coleta, filtragem e análise de vagas de emprego com IA.
Arquitetura: `Scrapers → Ingestion → Filtros → IA (Gemini) → API → Dashboard (Next.js)`.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLModel (SQLAlchemy 2.0), Alembic, Ruff, pytest + pytest-asyncio
- **Frontend**: Next.js 15 (App Router), React 19, TypeScript (strict), Tailwind CSS 4, shadcn + lucide-react
- **Database**: PostgreSQL 16
- **Proxy**: NGINX 1.27 (roteamento unificado frontend + API + docs)

## Dev Commands

```bash
# Full stack (recomendado)
cp .env.example .env  # edite credenciais
docker compose up -d --build

# Backend only
make install     # instala deps (bootstrap.sh --install-only)
make prepare     # setup completo do backend (venv + db + migrations)
make run-back    # bootstrap + API (uvicorn em :8000)

# Frontend only
make install-front
make prepare-front
make run-front   # Next.js dev server

# Local dev (backend + frontend, db via compose)
make run-dev

# Down
make down        # docker compose down
```

### Qualidade de Código

```bash
make lint        # ruff check --fix + format (src, tests)
make test        # pytest (use ARGS='caminho' para testes específicos)
make lint-front  # eslint (frontend)
make test-front  # delegate ao web/Makefile (placeholder se não existir)
```

### Logs e Acesso a Containers

```bash
make logs       # todos os logs do compose
make logs-back  # logs do backend
make logs-front # logs do frontend
make logs-nginx # logs do nginx
make sh-back    # shell no backend
make sh-front   # shell no frontend
make sh-db      # shell no banco
```

## CLI Tools

```bash
# Ingestão
jobscouter-ingest --source all --limit 20
jobscouter-ingest --source remoteok --keyword django --limit 10
jobscouter-ingest --continuous  # modo recorrente com controle de ciclos

# Análise
jobscouter-analyze --limit 20
```

## Source Structure

- `src/jobscouter/` — Python package root
  - `api/` — FastAPI app (`main.py`), dependências DI (`deps.py`), rotas (`routes/`)
  - `core/` — Configuração, logging, utilitários
  - `db/` — Modelos SQLModel e sessões
  - `scrapers/` — BaseScraper, RemoteOKScraper, RemotarScraper
  - `services/` — JobIngestionService, JobFilterService, AIAnalyzerService, ProfileEnricher
  - `schemas/` — Schemas Pydantic
  - `main.py` — CLI de ingestão (entry point: `jobscouter-ingest`)
  - `analyze_main.py` — CLI de análise (entry point: `jobscouter-analyze`)
- `web/` — Next.js frontend (App Router, src/structure)
- `alembic/` — Migrações do banco
- `tests/` — Testes do backend (pytest)
- `filters.yaml` — Configuração de filtros (keywords include/exclude)
- `docs/` — Documentação adicional

## API Endpoints

| Método | Path | Descrição |
|---|---|---|
| `GET` | `/api/v1/jobs` | Listagem com paginação (`page`, `size`, `status`, `min_score`) |
| `POST` | `/api/v1/control/sync/ingest` | Trigger de ingestão |
| `POST` | `/api/v1/control/sync/analyze` | Trigger de análise |
| `GET` | `/api/v1/config` | Obter config de filtros |
| `PATCH` | `/api/v1/config` | Atualizar config de filtros |

**Serviços expostos (deploy Docker):**
- Dashboard: `http://localhost/`
- API: `http://localhost/api/v1`
- Swagger Docs: `http://localhost/docs` (desabilitado em `APP_ENV=production`)

## Environment Variables

- `.env` na raiz (nunca commitar — usar `.env.example`)
- **Obrigatórias**: `GEMINI_API_KEY`, `POSTGRES_PASSWORD`
- **Importantes**: `DATABASE_URL` (local), `DATABASE_URL_DOCKER` (compose), `APP_ENV`, `NEXT_PUBLIC_API_BASE_PATH`
- Ver `.env.example` para lista completa com defaults

## Job Status Flow

```
pending → ready_for_ai | discarded → analyzed
```

- `pending` — sem match de include/exclude
- `ready_for_ai` — passou no filtro estático, aguarda IA
- `discarded` — vetada por palavra excluída
- `analyzed` — análise IA concluída (com score Gemini)

## Important Quirks

- **pytest**: `pythonpath = ["src"]` em pyproject.toml — imports são `jobscouter.*`, nunca `src.jobscouter.*`
- **Ruff**: line-length = 100, alvos `src` e `tests`
- **`APP_ENV=production`**: desabilita `/docs`, instala pacotes non-editable
- **`make test-front`**: delegate ao `web/Makefile`; pode ser placeholder
- **Backend entrypoint**: `jobscouter.api.main:app`
- **Frontend env vars**: `NEXT_PUBLIC_*` são build-time; mudança exige rebuild
- **Docker Compose**: container names são `jobscouter-backend`, `jobscouter-frontend`, `jobscouter-db`, `jobscouter-nginx`
- **NGINX**: proxy reverso unifica tudo em `localhost` (frontend raiz, API em `/api/v1`, docs em `/docs`)

## Commit Style

Conventional Commits: `type(scope): description`

Tipos: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

### Branch Naming

```
feat/nome-curto-da-mudanca
fix/descricao-curta-do-bug
docs/ajuste-documentacao
```

## Branch Protection

`main` protegida via GitHub Rulesets:
- Push direto bloqueado
- PR obrigatório
- CI deve estar verde (backend + frontend)
- Linear history (opcional)

## Pontos de Atenção

1. **Segredos**: nunca commitar `.env`. Usar `.env.example` com placeholders.
2. **Tests frontend**: `make test-front` pode ser placeholder — verificar `web/Makefile`.
3. **Filtros**: `filters.yaml` controla termos de busca e keywords de exclusão/inclusão.
4. **Modo contínuo**: `jobscouter-ingest --continuous` para ingestão recorrente.
5. **Produção**: `APP_ENV=production` desabilita docs e instala pacotes non-editable.
