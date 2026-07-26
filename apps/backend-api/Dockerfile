FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install uv --no-cache-dir
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN adduser --disabled-password --gecos "" appuser
COPY --from=builder /app/.venv /app/.venv
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/
RUN chown -R appuser:appuser /app
USER appuser
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 51080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:51080/health/live')"
CMD ["uvicorn", "ibreeze_backend.main:app", "--host", "0.0.0.0", "--port", "51080"]
