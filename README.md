# JobScouter

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Node LTS](https://img.shields.io/badge/Node-LTS-339933?logo=node.js&logoColor=white)](https://nodejs.org/)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-000000?logo=next.js)](https://nextjs.org/)
[![CI](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?logo=githubactions&logoColor=white)](./.github/workflows/tests.yml)
[![License MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)


## Visao Geral

O JobScouter resolve um problema pratico: buscar vagas em multiplas fontes, reduzir ruido de dados e transformar volume em decisao.

Em vez de apenas baixar anuncios, o sistema:

- centraliza a coleta de vagas;
- aplica filtros de negocio para remover ruido cedo;
- enriquece o resultado com analise de compatibilidade por IA;
- disponibiliza dados estruturados via API e dashboard web.

## Arquitetura do Ecossistema

Jornada do dado de ponta a ponta:

```text
Ingestao (Legacy Core)
  -> coleta e deduplica vagas por fonte/URL

Analise (Legacy Core)
  -> aplica filtros estaticos e, quando elegivel, score por IA

API Service (FastAPI)
  -> expoe consulta e gatilhos de sincronizacao de forma estruturada

Dashboard (Next.js)
  -> interface para visualizar e gerenciar oportunidades
```

Componentes principais:

- `BaseScraper`: contrato comum para novas fontes.
- `RemoteOKScraper` e `RemotarScraper`: conectores de ingestao.
- `JobIngestionService`: persistencia idempotente.
- `JobFilterService`: filtros estaticos por palavras-chave.
- `AIAnalyzerService`: compatibilidade por Gemini.

## Quick Start

### Modo recomendado (Deploy unificado com Docker Compose + NGINX)

```bash
cp .env.example .env
docker compose up -d --build
```

Servicos disponiveis apos subir:

- Entrada unica (NGINX): `http://localhost`
- Frontend via proxy: `http://localhost/`
- API via proxy: `http://localhost/api/v1`
- Swagger via proxy: `http://localhost/docs`

### Alternativas rapidas

Modo local (sem stack completa de containers):

```bash
make run-back   # apenas backend (inclui bootstrap + API)
make run-front  # apenas frontend
make run-dev    # backend + frontend locais (db via compose)
make down       # derruba os servicos do compose
```

Operacoes uteis no modo containerizado:

```bash
docker compose logs -f
docker compose down
```

## Configuracao de Ambiente

O projeto usa `.env` na raiz (backend e frontend).

Variaveis essenciais:

| Variavel | Obrigatoria | Default | Uso |
| --- | --- | --- | --- |
| `APP_ENV` | Nao | `development` | Ambiente de execucao; em `production` a API desabilita `/docs` e `/openapi.json` |
| `DATABASE_URL` | Sim | `postgresql+psycopg://postgres:postgres@localhost:5432/jobscouter` | Persistencia da API/CLI |
| `LOG_LEVEL` | Nao | `INFO` | Nivel de log |
| `REQUEST_TIMEOUT` | Nao | `20` | Timeout de requisicao HTTP |
| `REMOTEOK_API_URL` | Nao | `https://remoteok.com/api` | Fonte RemoteOK |
| `REMOTAR_BASE_URL` | Nao | `https://remotar.com.br` | Fonte Remotar |
| `REMOTAR_API_URL` | Nao | `https://api.remotar.com.br` | Fonte Remotar |
| `GEMINI_API_KEY` | Sim (analise IA) | - | Chave Gemini |
| `GEMINI_MODEL` | Nao | `gemini-1.5-flash-latest` | Modelo preferencial |
| `GEMINI_RETRY_DELAY_SECONDS` | Nao | `1.5` | Retry em rate limit |
| `DATABASE_URL_DOCKER` | Nao | `postgresql+psycopg://postgres:postgres@db:5432/jobscouter` | URL do banco usada no servico backend do Compose |
| `POSTGRES_DB` | Nao | `jobscouter` | Nome do banco no servico db |
| `POSTGRES_USER` | Nao | `postgres` | Usuario do banco no servico db |
| `POSTGRES_PASSWORD` | Sim | - | Senha do banco no servico db (defina valor forte) |
| `NEXT_PUBLIC_API_BASE_PATH` | Nao | `/api/v1` | Base relativa da API no frontend |
| `NEXT_PUBLIC_API_BASE_URL` | Nao | vazio | URL do backend para rewrite no modo local sem NGINX |

Observacao: para ambiente de producao, defina `APP_ENV=production` para desabilitar publicamente os endpoints de documentacao da API (`/docs`, `/openapi.json` e `/redoc`).
Observacao: variaveis `NEXT_PUBLIC_*` sao build-time no Next.js; alterar `NEXT_PUBLIC_API_BASE_PATH` ou `NEXT_PUBLIC_API_BASE_URL` exige rebuild da imagem frontend (`docker compose up -d --build`).

## Legado Funcional (Power User)

Embora o JobScouter ofereca experiencia completa via API + Dashboard, os modulos de ingestao e analise podem rodar de forma independente para pipelines customizados.

### CLI de ingestao

```bash
jobscouter-ingest --source all --limit 20
jobscouter-ingest --source remoteok --keyword django --limit 10
```

### CLI de analise

```bash
jobscouter-analyze --limit 20
```

Regras de status utilizadas no fluxo:

- `pending`: sem match de include/exclude.
- `ready_for_ai`: passou no filtro e segue para IA.
- `discarded`: vetada por palavra excluida.
- `analyzed`: analise concluida.

## API Service

Endpoints principais:

- `GET /api/v1/jobs`
- `POST /api/v1/control/sync/ingest`
- `POST /api/v1/control/sync/analyze`
- `GET /api/v1/config`
- `PATCH /api/v1/config`

### Listagem de vagas com paginacao

Query params suportados em `GET /api/v1/jobs`:

- `page` (opcional, default: `1`, minimo: `1`)
- `size` (opcional, default: `50`, minimo: `1`, maximo: `100`)
- `status` (opcional: `pending`, `ready_for_ai`, `discarded`, `analyzed`)
- `min_score` (opcional)

Exemplo de requisicao:

```bash
curl "http://127.0.0.1:8000/api/v1/jobs?page=2&size=20&status=analyzed&min_score=1"
```

Exemplo de resposta:

```json
{
  "items": [
    {
      "id": 101,
      "title": "Python Developer",
      "company": "Acme",
      "url": "https://example.com/jobs/101",
      "description_raw": "...",
      "status": "analyzed",
      "ai_score": 8,
      "ai_summary": "Boa aderencia para backend Python.",
      "ai_analysis_at": "2026-03-28T18:20:31Z"
    }
  ],
  "total": 240,
  "page": 2,
  "size": 20
}
```

## Frontend Web

Detalhes de desenvolvimento do dashboard Next.js (variaveis, scripts e comportamento de paginacao por URL) estao em [web/README.md](./web/README.md).

## Qualidade

```bash
make lint
make test
make lint-front
make test-front
```

Obs.: no estado atual, `make test-front` roda um placeholder definido em `web/package.json`.

## Roadmap e Extensibilidade

- Multi-nicho: estrutura pronta para expansao alem de vagas de tech.
- Novas fontes: onboarding de provedores adicionais com `BaseScraper`.
- IA de matching: evoluir para comparacao curriculo vs vaga.
- Maturidade de produto: ampliar observabilidade, testes frontend e deploy automatizado.

## Contribuicao

Fluxo de colaboracao e padroes de commit estao em [CONTRIBUTING.md](./CONTRIBUTING.md).

Ao abrir contribuicoes, use os templates:

- Issue de bug: [Bug Report](./.github/ISSUE_TEMPLATE/bug_report.md)
- Issue de feature: [Feature Request](./.github/ISSUE_TEMPLATE/feature_request.md)
- Pull request: [PR Template](./.github/pull_request_template.md)

## Licenca

Este projeto esta sob a licenca MIT. Veja [LICENSE](./LICENSE).
