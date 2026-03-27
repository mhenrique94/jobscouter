.PHONY: dev bootstrap bootstrap-only down

dev: bootstrap

bootstrap:
	./bootstrap.sh

bootstrap-only:
	./bootstrap.sh --bootstrap-only

down:
	@if docker compose version >/dev/null 2>&1; then \
		docker compose down; \
	elif command -v docker-compose >/dev/null 2>&1; then \
		docker-compose down; \
	else \
		echo "Docker Compose nao encontrado (docker compose ou docker-compose)"; \
		exit 1; \
	fi
