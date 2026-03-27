# Jobscouter Ingestion Module

Modulo de ingestao de vagas construido em Python 3.11+, com scrapers extensivos, schema unificado em PostgreSQL e persistencia idempotente.

## Arquitetura

- `BaseScraper`: contrato comum para qualquer nova fonte.
- `RemoteOKScraper`: consome a API JSON da RemoteOK.
- `RemotarScraper`: faz crawling HTML da Remotar e enriquece detalhes por vaga.
- `JobIngestionService`: normaliza o fluxo de persistencia e garante idempotencia.
- `Job`: schema SQLModel para PostgreSQL, com constraints para deduplicacao.

## Executando localmente

1. Suba o PostgreSQL com `docker compose up -d`.
2. Instale dependencias com `pip install -e .[dev]`.
3. Exporte as variaveis do `.env.example`.
4. Rode as migrations com `alembic upgrade head`.
5. Execute a ingestao com `jobscouter-ingest --source all --limit 20`.

## Fontes suportadas

- RemoteOK
- Remotar
