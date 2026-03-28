.PHONY: dev bootstrap bootstrap-only web web-bootstrap-only dev-full down lint lint-front test test-front front

dev: bootstrap

bootstrap:
	./bootstrap.sh

bootstrap-only:
	./bootstrap.sh --bootstrap-only

web:
	./bootstrap-web.sh

web-bootstrap-only:
	./bootstrap-web.sh --bootstrap-only

dev-full:
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
		echo "Ruff nao encontrado no ambiente virtual. Execute 'make bootstrap' primeiro."; \
		exit 1; \
	fi

test:
	@if [ -f .venv/bin/pytest ]; then \
		.venv/bin/pytest $(ARGS); \
	elif [ -f venv/bin/pytest ]; then \
		venv/bin/pytest $(ARGS); \
	else \
		echo "Ambiente virtual nao encontrado. Execute 'make bootstrap' primeiro."; \
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
