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

lint:
	@if [ "$(filter front,$(MAKECMDGOALS))" = "front" ]; then \
		$(MAKE) -C web lint front; \
	else \
		echo "Uso: make lint front"; \
		echo "Dica: make lint-front"; \
		exit 1; \
	fi

lint-front:
	@$(MAKE) -C web lint-front

test:
	@if [ "$(filter front,$(MAKECMDGOALS))" = "front" ]; then \
		$(MAKE) -C web test front; \
	else \
		echo "Uso: make test front"; \
		echo "Dica: make test-front"; \
		exit 1; \
	fi

test-front:
	@$(MAKE) -C web test-front

front:
	@:
