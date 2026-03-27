# Jobscouter: Ingestao + Analise IA

Projeto com dois modulos principais em Python 3.11+: ingestao de vagas e analise de compatibilidade por IA.

## Modulos do projeto

- Modulo 1 - Ingestao e filtragem estatica:
	- Coleta vagas das fontes suportadas, persiste no PostgreSQL com idempotencia e classifica status inicial (`pending`, `ready_for_ai`, `discarded`).
	- Comando: `jobscouter-ingest`.
- Modulo 2 - Analise por IA:
	- Processa vagas `ready_for_ai`, calcula score de compatibilidade, gera resumo e fecha o processamento com status `analyzed`.
	- Comando: `jobscouter-analyze`.

## Arquitetura

- `BaseScraper`: contrato comum para qualquer nova fonte.
- `RemoteOKScraper`: consome a API JSON da RemoteOK.
- `RemotarScraper`: faz crawling HTML da Remotar e enriquece detalhes por vaga.
- `JobIngestionService`: normaliza o fluxo de persistencia e garante idempotencia.
- `JobFilterService`: classifica vagas com filtros estaticos antes da analise por IA.
- `AIAnalyzerService`: analisa vagas `ready_for_ai` com Gemini e atribui score de compatibilidade.
- `Job`: schema SQLModel para PostgreSQL, com constraints para deduplicacao e status de processamento.

## Modulo 1: Ingestao e Filtragem Estatica

Após cada upsert, a vaga e classificada imediatamente para reduzir custo de processamento de IA.

### Status da vaga

- `pending`: vaga sem match de include/exclude (fila para revisao manual posterior).
- `ready_for_ai`: vaga aprovada por conter ao menos uma `include_keyword`.
- `discarded`: vaga descartada por conter ao menos uma `exclude_keyword`.
- `analyzed`: vaga ja analisada; este status nao e sobrescrito pela filtragem estatica.

### Motivo de descarte

- `filter_reason`: preenchido apenas quando `status=discarded`, com formato `Palavra excluida: <termo>`.

### Arquivo de regras

As regras sao lidas de `filters.yaml` na raiz do projeto:

```yaml
search_terms: ["python", "django", "vue", "vuejs", "fullstack", "javascript", "nuxt"]

filters:
	exclude_keywords: ["Presencial", "Híbrido", "Junior", "Estágio", "PHP", "Java", "C#", "Rust"]
	include_keywords: ["Remote", "Remoto", "Home Office", "Django", "Vue", "Python", "Fullstack", "Pleno", "Mid-level"]
```

#### Termos de busca (search_terms)

A secao `search_terms` define quais termos-chave o scraper ira buscar ativamente em cada fonte.
Quando o comando `jobscouter-ingest` e executado **sem o parametro `--keyword`**, ele itera sobre todos esses termos automaticamente, garantindo cobertura ampla e idempotencia (deduplicacao por constraints DB).

#### Prioridade de classificacao

1. Se encontrar qualquer `exclude_keyword`, define `discarded`.
2. Caso passe pelo exclude e encontre alguma `include_keyword`, define `ready_for_ai`.
3. Caso contrario, define `pending`.

O matching e case-insensitive sobre titulo + descricao da vaga.

## Executando localmente

1. Suba o PostgreSQL com `docker compose up -d`.
2. Instale dependencias com `pip install -e .[dev]`.
3. Exporte as variaveis do `.env.example`.
4. Rode as migrations com `alembic upgrade head`.
5. Execute a ingestao com `jobscouter-ingest --source all --limit 20`.
6. Execute a analise com `jobscouter-analyze --limit 20`.

## Modulo 2: Analise por IA (Gemini)

O comando `jobscouter-analyze` processa apenas vagas com `status=ready_for_ai`.
Para cada vaga processada, o sistema preenche:

- `ai_score`: score inteiro de 0 a 10.
- `ai_summary`: resumo curto da analise.
- `ai_analysis_at`: timestamp da analise.

Ao concluir a vaga, o status e atualizado para `analyzed`.

### Regras de robustez

- Prompt objetivo e seco, focado em aderencia tecnica ao perfil alvo.
- Retorno exigido em JSON estrito com `score` e `summary`.
- Vagas claramente nao-dev (ex.: contador, vendedor, design) recebem `score=0` imediatamente.
- Em rate limit (`ResourceExhausted`), o servico aplica delay curto e retry.
- Se `gemini-1.5-flash` nao estiver disponivel para a chave atual, o servico tenta fallbacks Flash disponiveis automaticamente.

### Variaveis de ambiente da IA

- `GEMINI_API_KEY`: chave da API Gemini.
- `GEMINI_MODEL`: modelo preferencial (padrao: `gemini-1.5-flash-latest`).
- `GEMINI_RETRY_DELAY_SECONDS`: atraso do retry em rate limit (padrao: `1.5`).

### Configuracao recomendada no .env

Use este baseline para evitar erro de modelo indisponivel:

```env
GEMINI_API_KEY=<sua_chave>
GEMINI_MODEL=models/gemini-2.5-flash
GEMINI_RETRY_DELAY_SECONDS=1.5
```

### Exemplo de execucao

- Ingestao: `jobscouter-ingest --source all --limit 20`
- Analise: `jobscouter-analyze --limit 20`

### Troubleshooting (IA)

- Erro `GEMINI_API_KEY nao configurada`:
	- Garanta que `GEMINI_API_KEY` esteja definida no `.env`.
	- Rode com: `set -a && source .env && set +a` antes do comando.

- Erro `NotFound ... model ... is not found for API version v1beta`:
	- Algumas chaves nao possuem `gemini-1.5-flash` habilitado.
	- O servico tenta fallback automatico para modelos Flash disponiveis.
	- Se quiser forcar um modelo conhecido na sua conta, defina `GEMINI_MODEL` (ex.: `models/gemini-2.5-flash`).

- Warning de deprecacao da biblioteca `google.generativeai`:
	- O warning nao bloqueia execucao.
	- O projeto segue este pacote por compatibilidade atual; migracao futura para `google.genai` e recomendada.

### Listar modelos disponiveis da sua chave

Use o comando abaixo para descobrir quais modelos Flash aceitam `generateContent` na sua conta:

```bash
set -a && source .env && set +a
/home/marcelo/Github/jobscouter/.venv/bin/python - <<'PY'
import os
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
for model in genai.list_models():
		methods = getattr(model, "supported_generation_methods", []) or []
		if "generateContent" in methods and "flash" in model.name.lower():
				print(model.name)
PY
```

## Parametros do Modulo 1 (Ingestao)

A busca e finita por padrao: sem `--continuous`, o comando executa 1 ciclo e encerra.

### Parametros

- `--source {all,remoteok,remotar}`: escolhe a fonte.
- `--keyword TERMO`: busca explicita por um termo especifico. Quando omitido, o scraper itera sobre todos os termos definidos em `search_terms` no `filters.yaml`. Cada busca respeita a idempotencia do banco de dados.
- `--limit N`: limita a quantidade de vagas processadas por fonte **e por cada termo** em cada ciclo.
- `--max-pages N`: limita quantas paginas da listagem da API da Remotar podem ser consultadas por ciclo.
- `--continuous`: habilita modo continuo (ciclos sucessivos).
- `--poll-interval-seconds N`: intervalo entre ciclos no modo continuo (padrao: `300`).
- `--max-cycles N`: encerra apos N ciclos (somente com `--continuous`).
- `--max-duration-seconds N`: encerra quando atingir N segundos totais (somente com `--continuous`).
- `--max-empty-cycles N`: encerra apos N ciclos seguidos sem vagas novas/atualizadas (somente com `--continuous`).

### Timeout de rede

- `REQUEST_TIMEOUT`: timeout por requisicao HTTP em segundos (padrao: `20`).

### Exemplos

- Rodada unica com limite por fonte (itera sobre todos os `search_terms` do YAML): `jobscouter-ingest --source all --limit 20`
- Rodada unica com busca especifica: `jobscouter-ingest --source remoteok --keyword django --limit 10`
- Ambas fontes, somente termo 'python': `jobscouter-ingest --source all --keyword python --limit 5`
- Rodando continuamente, com pausa de 2 minutos e limite de 10 ciclos: `jobscouter-ingest --source all --continuous --poll-interval-seconds 120 --max-cycles 10`
- Rodando continuamente por no maximo 1 hora: `jobscouter-ingest --source all --continuous --max-duration-seconds 3600`
- Rodando ate ficar 3 ciclos seguidos sem novidades: `jobscouter-ingest --source all --continuous --max-empty-cycles 3`
- Forcando no maximo 2 paginas da API da Remotar por ciclo: `jobscouter-ingest --source remotar --max-pages 2`

### Busca ativa por termos

Por padrao, o scraper itera sobre todos os `search_terms` definidos no arquivo de configuracao.
Cada termo dispara uma busca independente em cada fonte, com um delay automatico de 2 segundos entre termos para reduzir risco de bloqueio por frequencia:

**Exemplo de fluxo:**

```
Ciclo 1
  RemoteOK + 'python'    -> 10 vagas
  (sleep 2s)
  RemoteOK + 'django'    -> 4 vagas
  (sleep 2s)
  ... continua para todos os termos ...
  Remotar + 'python'     -> 10 vagas
  (sleep 2s)
  ... e assim por diante
```

**Idempotencia garantida**: mesmo se uma vaga aparecer em multiplos termos (ex.: Python + Django),
os constraints unicos no banco de dados (`source` + `external_id`, `source` + `url`) impedem duplicatas.
A vaga e inserida apenas uma vez, mas seu `last_seen_at` e atualizado em cada ciclo.

#### Comportamento do Remotar com busca

- **Com termo**: tenta buscar via `/search?q={termo}` primeiro. Se falhar (404), faz fallback automatico para a API com parametro de busca.
- **Sem termo** (home page): consulta a listagem da home e, se vazia, faz fallback para API.

Esse comportamento garante resiliencia: mesmo que o endpoint de busca mude ou nao exista, o scraper continua funcionando via API.

## Fontes suportadas

- RemoteOK
- Remotar
