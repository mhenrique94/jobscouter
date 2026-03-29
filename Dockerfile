FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY filters.yaml ./filters.yaml
COPY docker/backend-entrypoint.sh ./docker/backend-entrypoint.sh

ARG APP_ENV=development
ARG EDITABLE=
RUN if [ "$EDITABLE" = "true" ]; then \
            pip install --no-cache-dir -e .; \
        elif [ "$EDITABLE" = "false" ]; then \
            pip install --no-cache-dir .; \
        elif [ "$APP_ENV" = "production" ]; then \
            pip install --no-cache-dir .; \
        else \
            pip install --no-cache-dir -e .; \
        fi
RUN chmod +x ./docker/backend-entrypoint.sh

EXPOSE 8000

CMD ["./docker/backend-entrypoint.sh"]
