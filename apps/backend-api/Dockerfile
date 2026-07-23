FROM python:3.12-slim AS base
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev
COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/
EXPOSE 51080
CMD ["/app/.venv/bin/uvicorn", "ibreeze_backend.main:app", "--host", "0.0.0.0", "--port", "51080"]
