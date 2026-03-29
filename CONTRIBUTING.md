# Contributing to JobScouter

Obrigado por contribuir com o JobScouter.

Este guia cobre o setup de desenvolvimento, padroes de commit e fluxo de pull request.

## Codigo de Conduta

Seja respeitoso, objetivo e colaborativo em issues, PRs e revisoes.

## Requisitos

- Python 3.11+
- Node.js LTS
- Docker com Docker Compose
- Git

## Setup de Desenvolvimento

1. Clone o repositorio e entre na pasta do projeto.
2. Crie o arquivo de ambiente.

```bash
cp .env.example .env
```

3. Suba a stack completa com Docker Compose (db + backend + frontend + nginx).

```bash
docker compose up -d --build
```

4. Valide os endpoints principais.

```bash
curl -i http://localhost/
curl -i http://localhost/api/v1/jobs
```

Para manter `/docs` e `/openapi.json` acessiveis apenas fora de producao, use `APP_ENV=development` em ambientes de contribuicao e `APP_ENV=production` em deploy de producao.

Alternativas em modo local (sem stack completa):

```bash
make run-dev
make run-back
make run-front
```

Encerrar stack de containers:

```bash
docker compose down
```

## Protecao da Branch Main

A branch `main` e protegida via **GitHub Rulesets** (`Settings > Rules > Rulesets`).

### Configuracao recomendada do Ruleset

**Ruleset Name:** `main`
**Enforcement status:** `Active`
**Bypass list:** vazia (nenhuma role/agente com bypass)

**Target branches:** adicionar `main` via `Add target > Include by pattern`.

**Regras a ativar:**

| Regra | Ativar? | Motivo |
|---|---|---|
| Restrict deletions | Sim (padrao) | Impede remocao acidental da branch |
| Restrict updates | **Sim** | Bloqueia push direto na `main` |
| Require linear history | Opcional | Historico mais limpo, sem merge commits |
| Require a pull request before merging | **Sim** | Toda mudanca passa por revisao |
| Require status checks to pass | **Sim** | CI deve estar verde antes do merge |
| Block force pushes | Sim (padrao) | Impede reescrita de historico |
| Automatically request Copilot code review | Opcional | Revisao automatica por IA |

### Status checks obrigatorios

Ao ativar **Require status checks to pass**, adicione os dois jobs do workflow `.github/workflows/tests.yml`:

- `Backend (pytest)`
- `Frontend (npm test)`

Marque tambem **Require branches to be up to date** para garantir que nenhum PR seja mergeado desatualizado em relacao a `main`.

### Resultado esperado

Com essas regras ativas, qualquer colaborador precisara:

1. criar uma branch a partir de `main`;
2. abrir um PR usando o template;
3. aguardar o CI passar (backend + frontend);
4. receber ao menos uma aprovacao (se configurado);
5. somente entao conseguir fazer merge.

Push direto na `main` sera rejeitado.

---

## Fluxo de Trabalho

1. Crie uma branch a partir de `main`.
2. Implemente uma mudanca por PR, com escopo pequeno e claro.
3. Execute validacoes locais.
4. Abra o PR usando o template.

Sugestao de nome de branch:

```text
feat/nome-curto-da-mudanca
fix/descricao-curta-do-bug
docs/ajuste-documentacao
```

## Padrao de Commits

Este projeto adota Conventional Commits.

Formato:

```text
type(scope): descricao curta
```

Tipos comuns:

- `feat`: nova funcionalidade
- `fix`: correcao de bug
- `docs`: alteracao de documentacao
- `refactor`: refatoracao sem alterar comportamento
- `test`: adicao/ajuste de testes
- `chore`: tarefas de manutencao

Exemplos:

```text
feat(api): adiciona filtro por score minimo
fix(scraper): corrige fallback da busca na Remotar
docs(readme): reorganiza quick start
```

## Checklist Local Antes do PR

Execute na raiz:

```bash
make lint
make test
make lint-front
make test-front
docker compose config
```

Smoke test recomendado quando houver mudancas de deploy/infra:

```bash
docker compose up -d --build
curl -i http://localhost/
curl -i http://localhost/api/v1/jobs
docker compose down
```

Observacao: atualmente `make test-front` executa um placeholder no frontend.

## Seguranca de Segredos

Para evitar alertas de secret scanning (GitGuardian/GitHub Advanced Security), siga estas regras:

- Nunca commitar `.env`.
- Em `.env.example`, use apenas placeholders (`CHANGE_ME_*`) para chaves e senhas.
- Evite defaults sensiveis em `docker-compose.yml` (ex.: senha padrao hardcoded).
- Prefira variaveis obrigatorias no compose para credenciais criticas.

Checklist rapido de seguranca antes de abrir PR:

```bash
docker compose config
git diff -- .env .env.example docker-compose.yml
```

Se aparecer qualquer valor real de credencial no diff, remova antes do push.

## Pull Requests

Use o template em `.github/pull_request_template.md` e inclua:

- contexto do problema
- o que foi alterado
- como validar
- riscos e impactos

Checklist esperado no PR:

- escopo objetivo
- sem segredos em codigo ou logs
- documentacao atualizada quando necessario

## Report de Bugs e Ideias

Abra uma issue com o template apropriado:

- Bug: `.github/ISSUE_TEMPLATE/bug_report.md`
- Feature: `.github/ISSUE_TEMPLATE/feature_request.md`

Inclua passos claros de reproducao, comportamento esperado e contexto de ambiente.

## Areas para Contribuir

- novas fontes de vagas (scrapers)
- melhorias de score/explicabilidade da IA
- testes frontend
- observabilidade e confiabilidade operacional
- UX do dashboard
