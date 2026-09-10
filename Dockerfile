FROM python:3.12-slim AS builder
WORKDIR /build
RUN pip install --no-cache-dir uv==0.12.12
COPY pyproject.toml uv.lock ./
COPY app ./app
RUN uv sync --frozen --no-dev --no-editable --no-cache

FROM python:3.12-slim
RUN groupadd --gid 10001 bot && useradd --uid 10001 --gid bot --create-home bot
WORKDIR /app
COPY --from=builder /build/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_HOST=0.0.0.0 \
    DATA_DIR=/app/data \
    ARTIFACT_DIR=/app/artifacts \
    LOG_DIR=/app/logs
RUN mkdir -p /app/data /app/artifacts /app/logs && chown -R bot:bot /app
USER bot
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('APP_PORT','8000')+'/readyz',timeout=4)"
CMD ["python", "-m", "app"]
