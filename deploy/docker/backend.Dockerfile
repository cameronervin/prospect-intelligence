FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN pip install --no-cache-dir "uv>=0.11,<1" \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
COPY backend/app ./app
COPY backend/evaluation/datasets/golden ./evaluation/datasets/golden
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini
RUN uv sync --frozen --no-dev \
    && chown -R root:root /app \
    && chmod -R a-w /app

USER 10001:10001
EXPOSE 8000

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS e2e

COPY --chown=0:0 backend/tests ./tests

CMD ["uvicorn", "tests.e2e_app:create_e2e_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS production
