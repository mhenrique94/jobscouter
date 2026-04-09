# SSE Activity Panel — Design

**Data:** 2026-04-08
**Branch:** `marcelo/feat-enriquecimento-contexto-agentes`

---

## Problema

O dashboard não dava feedback sobre o que acontecia durante ingestão e análise. O usuário disparava uma operação, recebia um 202 e ficava cego — o único caminho era abrir um drawer de logs que carregava um snapshot estático e exigia atualização manual.

## Solução

Painel persistente fixo no rodapé com logs em tempo real via Server-Sent Events (SSE), substituindo o drawer de logs.

---

## Decisões de arquitetura

### SSE em vez de WebSocket

A comunicação é **unidirecional**: o servidor empurra dados para o cliente. SSE é suficiente, mais simples, funciona sobre HTTP padrão e o `EventSource` do browser reconecta automaticamente. WebSocket seria overkill.

### TaskRegistry em memória com `threading.Lock`

O registro de tasks é um dicionário compartilhado acessado por dois contextos diferentes:

- **Event loop (asyncio):** endpoint SSE lê o snapshot; `_run_ingest_sync` e `_run_analyze_sync` (funções `async`) escrevem.
- **Thread pool:** `_run_assertiveness_cleanup_sync` (função `sync`) escreve — fora do event loop.

O `Lock` protege contra race condition entre a thread do cleanup e o event loop do SSE. Sem o lock, o dict poderia ser modificado e lido simultaneamente. Funções `async` entre si não precisam de lock (o event loop garante execução cooperativa).

### Sem dependências novas

Toda a implementação usa stdlib Python (`threading`, `datetime`, `json`, `pathlib`) e o que já existia no projeto (`FastAPI`, `EventSource` nativo do browser, `Tailwind`, `lucide-react`).

---

## Componentes implementados

### Backend

**`src/jobscouter/core/task_registry.py`**
- `TaskState`: dataclass com `id`, `type`, `status`, `detail`, timestamps
- `TaskRegistry`: singleton com `start()`, `update()`, `finish()`, `snapshot()`, `evict_finished()`
- `task_registry`: instância global importada pelas background tasks e pelo endpoint SSE

**`src/jobscouter/api/routes/control.py` — `GET /control/stream`**
- Bloqueado em produção (consistente com `/logs`)
- Burst inicial: últimas 100 linhas do log file
- Loop a cada 0.75s: tail do arquivo por offset + snapshot das tasks
- Aplica redact de credenciais nas linhas novas
- Header `X-Accel-Buffering: no` para evitar buffer do nginx

**Background tasks integradas ao registry:**
- `_run_ingest_sync`: atualiza detalhe a cada termo/fonte (`remotar/python: 3 novas`)
- `_run_analyze_sync`: progresso numérico (`12/50 analisadas`)
- `_run_assertiveness_cleanup_sync`: contadores por lote (`excluidas=N preservadas=M`)

**`src/jobscouter/core/logging.py` — `_LocalTimeFormatter`**
- Sobrescreve `formatTime` com `datetime.fromtimestamp().astimezone()`
- Respeita a variável de ambiente `TZ` — corrige horário UTC em containers Docker
- `docker-compose.yml` recebe `TZ: ${TZ:-America/Sao_Paulo}`

### Frontend

**`web/src/hooks/useTaskStream.ts`**
- Conecta ao SSE com `EventSource` nativo
- Acumula até 500 linhas (evita crescimento ilimitado em memória)
- Retorna `{ logs, tasks, connected }`

**`web/src/components/ActivityPanel.tsx`**
- Painel fixo `bottom-0`, transição de altura `h-8` ↔ `h-72`
- Barra inteira clicável (botão semântico) com `hover` de feedback
- Colapsado: dot de conexão com glow, label "output", chips das tasks em execução (máx. 2 + `+N`), contador de linhas
- Expandido: status de cada task com detalhe, área de log com fonte mono, auto-scroll inteligente (desativa se o usuário rolar para cima), botão "↓ ir para o fim"
- Log coloring: `ERROR`→rose, `WARNING`→amber, `INFO`→zinc-500, `DEBUG`→zinc-700
- Responsivo: label e contador somem em `xs`, chips limitados a 2

**`web/src/app/layout.tsx`** — `ActivityPanel` adicionado no root layout com `pb-8` no body.

**`web/src/app/page.tsx`** — drawer de logs e estados associados removidos.
