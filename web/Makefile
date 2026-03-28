.PHONY: lint lint-front test test-front front

lint:
	@if [ "$(filter front,$(MAKECMDGOALS))" = "front" ]; then \
		npm run lint; \
	else \
		echo "Uso: make lint front"; \
		echo "Dica: make lint-front"; \
		exit 1; \
	fi

lint-front:
	@npm run lint

test:
	@if [ "$(filter front,$(MAKECMDGOALS))" = "front" ]; then \
		npm run test; \
	else \
		echo "Uso: make test front"; \
		echo "Dica: make test-front"; \
		exit 1; \
	fi

test-front:
	@npm run test

front:
	@:
