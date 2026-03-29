# JobScouter Web

Frontend do JobScouter construído com Next.js (App Router) para visualizar vagas, acionar sincronizações e acompanhar análise por IA.

## Requisitos

- Node.js LTS
- API do JobScouter disponível (local ou via Docker Compose)

## Configuração

Variáveis de ambiente usadas pelo frontend:

- `NEXT_PUBLIC_API_BASE_PATH` (default: `/api/v1`)
- `NEXT_PUBLIC_API_BASE_URL` (opcional, útil para desenvolvimento sem proxy)

Exemplo de `.env.local`:

```bash
NEXT_PUBLIC_API_BASE_PATH=/api/v1
# NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## Desenvolvimento

```bash
npm install
npm run dev
```

Aplicação disponível em `http://localhost:3000`.

## Paginacao no Dashboard

A lista de vagas usa paginação de backend (`GET /jobs?page=&size=`) e sincroniza com a URL.

- A página atual é controlada por query param, exemplo: `/?page=2`.
- Navegar na paginação atualiza a URL e dispara novo fetch.
- O loading é exibido durante troca de página para sinalizar atualização.
- O contrato esperado da API é:

```json
{
	"items": [],
	"total": 0,
	"page": 1,
	"size": 50
}
```

## Scripts úteis

```bash
npm run lint
npm run build
```
