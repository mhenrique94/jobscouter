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

## Controle de execucao da busca

A busca e finita por padrao: sem `--continuous`, o comando executa 1 ciclo e encerra.

### Parametros

- `--source {all,remoteok,remotar}`: escolhe a fonte.
- `--limit N`: limita a quantidade de vagas processadas por fonte em cada ciclo.
- `--max-pages N`: limita quantas paginas da listagem da API da Remotar podem ser consultadas por ciclo.
- `--continuous`: habilita modo continuo (ciclos sucessivos).
- `--poll-interval-seconds N`: intervalo entre ciclos no modo continuo (padrao: `300`).
- `--max-cycles N`: encerra apos N ciclos (somente com `--continuous`).
- `--max-duration-seconds N`: encerra quando atingir N segundos totais (somente com `--continuous`).
- `--max-empty-cycles N`: encerra apos N ciclos seguidos sem vagas novas/atualizadas (somente com `--continuous`).

### Timeout de rede

- `REQUEST_TIMEOUT`: timeout por requisicao HTTP em segundos (padrao: `20`).

### Exemplos

- Rodada unica com limite por fonte: `jobscouter-ingest --source all --limit 20`
- Rodando continuamente, com pausa de 2 minutos e limite de 10 ciclos: `jobscouter-ingest --source all --continuous --poll-interval-seconds 120 --max-cycles 10`
- Rodando continuamente por no maximo 1 hora: `jobscouter-ingest --source all --continuous --max-duration-seconds 3600`
- Rodando ate ficar 3 ciclos seguidos sem novidades: `jobscouter-ingest --source all --continuous --max-empty-cycles 3`
- Forcando no maximo 2 paginas da API da Remotar por ciclo: `jobscouter-ingest --source remotar --max-pages 2`

## Fontes suportadas

- RemoteOK
- Remotar
