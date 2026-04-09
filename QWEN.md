# QWEN.md — JobScouter

## Visao Geral

**JobScouter** é um sistema completo de coleta, filtragem e análise de vagas de emprego com IA. O projeto resolve o problema de buscar vagas em múltiplas fontes, reduzir ruído de dados e transformar volume em decisão.

### Componentes Principais

| Componente | Tecnologia | Descrição |
|---|---|---|
| **Backend (Ingestion + API)** | Python 3.11+, FastAPI, SQLModel | Scrapers extensíveis, filtros estáticos, análise IA (Gemini), API REST |
| **Frontend (Dashboard)** | Next.js 15, React 19, Tailwind CSS 4, TypeScript | Dashboard para visualizar vagas, acionar sincronizações e acompanhar análise |
| **Database** | PostgreSQL 16 | Persistência das vagas e configurações |
| **Proxy Reverso** | NGINX 1.27 | Roteamento unificado (frontend + API + docs) |

### Arquitetura — Fluxo de Dados

```
Ingestao (Scrapers) -> deduplica vagas por fonte/URL
       ↓
Analise (Filter + IA) -> filtros estaticos + score por Gemini
       ↓
API Service (FastAPI) -> expoe consulta e triggers de sincronizacao
       ↓
Dashboard (Next.js) -> interface para visualizar e gerenciar oportunidades
```

### Scrapers Disponíveis

- **RemoteOKScraper** — conector para RemoteOK API
- **RemotarScraper** — conector para Remotar (Brasil)
- **BaseScraper** — contrato base para novas fontes

### Serviços Core

- **JobIngestionService** — persistência idempotente de vagas
- **JobFilterService** — filtros por palavras-chave (include/exclude)
- **AIAnalyzerService** — compatibilidade e scoring por IA (Gemini)
- **ProfileEnricher** — expansão de perfil de busca via IA

## Estrutura de Diretórios

```
jobscouter/
├── src/jobscouter/       # Código Python do backend
│   ├── api/              # FastAPI app e rotas
│   │   ├── main.py       # App FastAPI principal
│   │   ├── deps.py       # Dependencias de DI
│   │   └── routes/       # Endpoints da API
│   ├── core/             # Configuracao, logging, utilitarios
│   ├── db/               # Modelos SQLModel e sessoes
│   ├── scrapers/         # Scrapers (base, remoteok, remotar)
│   ├── services/         # Ingestion, filter, analyzer, profile_enricher
│   ├── schemas/          # Schemas Pydantic
│   ├── main.py           # CLI de ingestao (jobscouter-ingest)
│   └── analyze_main.py   # CLI de analise (jobscouter-analyze)
├── web/                  # Frontend Next.js
│   ├── src/              # Componentes, paginas, hooks
│   ├── package.json
│   └── ...
├── alembic/              # Migracoes do banco
├── filters.yaml          # Configuracao de filtros (keywords)
├── docker-compose.yml    # Stack completa (db + backend + frontend + nginx)
├── Dockerfile            # Imagem do backend
├── nginx.conf            # Configuracao do proxy NGINX
├── Makefile              # Comandos de desenvolvimento
├── bootstrap.sh          # Setup do backend (venv + db + migrations + uvicorn)
├── bootstrap-web.sh      # Setup do frontend
└── dev-full.sh           # Modo dev completo (backend + frontend locais)
```

## Comandos Essenciais

### Deploy Unificado (Recomendado)

```bash
cp .env.example .env
# Edite .env com suas credenciais (GEMINI_API_KEY, POSTGRES_PASSWORD)
docker compose up -d --build
```

Servicos disponíveis:
- **Dashboard**: `http://localhost/`
- **API**: `http://localhost/api/v1`
- **Swagger Docs**: `http://localhost/docs`

### Desenvolvimento Local (sem Docker Compose completo)

```bash
make run-back   # apenas backend (bootstrap + API)
make run-front  # apenas frontend
make run-dev    # backend + frontend locais (db via compose)
make down       # derruba servicos do compose
```

### Qualidade de Código

```bash
make lint       # ruff check + format (backend)
make test       # pytest (backend)
make lint-front # eslint (frontend)
make test-front # placeholder (frontend)
```

### Logs e Acesso a Containers

```bash
make logs       # todos os logs
make logs-back  # logs do backend
make logs-front # logs do frontend
make logs-nginx # logs do nginx
make sh-back    # shell no backend
make sh-front   # shell no frontend
make sh-db      # shell no banco
```

### CLIs de Ingestão e Análise (Modo Standalone)

```bash
jobscouter-ingest --source all --limit 20
jobscouter-ingest --source remoteok --keyword django --limit 10
jobscouter-analyze --limit 20
```

## Variaveis de Ambiente

| Variavel | Obrigatoria | Default | Uso |
|---|---|---|---|
| `APP_ENV` | Não | `development` | Ambiente; `production` desabilita `/docs` |
| `DATABASE_URL` | Sim | `postgresql+psycopg://postgres:postgres@localhost:5432/jobscouter` | URL do banco |
| `GEMINI_API_KEY` | Sim (para IA) | - | Chave Gemini |
| `POSTGRES_PASSWORD` | Sim | - | Senha do PostgreSQL |
| `NEXT_PUBLIC_API_BASE_PATH` | Não | `/api/v1` | Base relativa da API no frontend |

Veja `.env.example` para lista completa.

## API Endpoints

| Metodo | Path | Descrição |
|---|---|---|
| `GET` | `/api/v1/jobs` | Listagem de vagas com paginacao (`page`, `size`, `status`, `min_score`) |
| `POST` | `/api/v1/control/sync/ingest` | Trigger de ingestao |
| `POST` | `/api/v1/control/sync/analyze` | Trigger de analise |
| `GET` | `/api/v1/config` | Obter config de filtros |
| `PATCH` | `/api/v1/config` | Atualizar config de filtros |

### Status de Vagas

- `pending` — sem match de include/exclude
- `ready_for_ai` — passou no filtro, segue para IA
- `discarded` — vetada por palavra excluida
- `analyzed` — analise concluida

## Convenções de Desenvolvimento

### Commits

Projeto usa **Conventional Commits**:

```
type(scope): descricao curta
```

Tipos: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

### Branch Naming

```
feat/nome-curto-da-mudanca
fix/descricao-curta-do-bug
docs/ajuste-documentacao
```

### Python

- Linter/formatter: **Ruff** (`line-length = 100`)
- Testes: **pytest** com **pytest-asyncio** (modo auto)
- ORM: **SQLModel** (SQLAlchemy 2.0)
- Migracoes: **Alembic**

### Frontend

- **Next.js 15** com App Router
- **TypeScript** strict
- **Tailwind CSS 4**
- **shadcn** + **lucide-react** para componentes
- **ESLint** com `eslint-config-next`

### Protecao da Branch Main

Branch `main` protegida via GitHub Rulesets:
- Push direto bloqueado
- PR obrigatorio
- CI deve estar verde (backend + frontend tests)
- Require linear history (opcional)

## Pontos de Atenção

1. **Segredos**: nunca commitar `.env`. Usar apenas placeholders em `.env.example`.
2. **Tests frontend**: atualmente `make test-front` é um placeholder — testes frontend ainda não estão configurados.
3. **Filtros**: `filters.yaml` controla termos de busca e keywords de exclusão/inclusão.
4. **Modo contínuo**: `jobscouter-ingest --continuous` permite ingestão recorrente com controle de ciclos.
5. **Produção**: definir `APP_ENV=production` desabilita endpoints de documentação e instala pacotes em modo não-editável.
