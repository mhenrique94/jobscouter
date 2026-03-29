.PHONY: install prepare run-back install-front prepare-front run-front run-dev down lint lint-front test test-front front logs logs-back logs-front logs-nginx sh-back sh-front sh-db

install:
	./bootstrap.sh --install-only

prepare:
	./bootstrap.sh --bootstrap-only

run-back:
	./bootstrap.sh

install-front:
	./bootstrap-web.sh --install-only

prepare-front:
	./bootstrap-web.sh --bootstrap-only

run-front:
	./bootstrap-web.sh

run-dev:
	./dev-full.sh

down:
	@if docker compose version >/dev/null 2>&1; then \
		docker compose down; \
	elif command -v docker-compose >/dev/null 2>&1; then \
		docker-compose down; \
	else \
		echo "Docker Compose nao encontrado (docker compose ou docker-compose)"; \
		exit 1; \
	fi

logs:
	@docker compose logs -f

logs-back:
	@docker logs -f jobscouter-backend

logs-front:
	@docker logs -f jobscouter-frontend

logs-nginx:
	@docker logs -f jobscouter-nginx

sh-back:
	@docker exec -it jobscouter-backend sh

sh-front:
	@docker exec -it jobscouter-frontend sh

sh-db:
	@docker exec -it jobscouter-db sh

lint-front:
	@$(MAKE) -C web lint-front

lint:
	@if [ -f .venv/bin/ruff ]; then \
		.venv/bin/ruff check --fix src tests; \
		.venv/bin/ruff format src tests; \
	elif [ -f venv/bin/ruff ]; then \
		venv/bin/ruff check --fix src tests; \
		venv/bin/ruff format src tests; \
	else \
		echo "Ruff nao encontrado no ambiente virtual. Execute 'make install' primeiro."; \
		exit 1; \
	fi

test:
	@if [ -f .venv/bin/pytest ]; then \
		.venv/bin/pytest $(ARGS); \
	elif [ -f venv/bin/pytest ]; then \
		venv/bin/pytest $(ARGS); \
	else \
		echo "Ambiente virtual nao encontrado. Execute 'make install' primeiro."; \
		exit 1; \
	fi

test-front:
	@if [ -f web/package.json ]; then \
		$(MAKE) -C web test-front; \
	else \
		npm run test; \
	fi

front:
	@:
