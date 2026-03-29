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

RUN pip install --no-cache-dir -e .
RUN chmod +x ./docker/backend-entrypoint.sh

EXPOSE 8000

CMD ["./docker/backend-entrypoint.sh"]
