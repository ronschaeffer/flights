# --- Builder stage ---
FROM python:3.11-slim AS builder
WORKDIR /build

RUN pip install --no-cache-dir poetry poetry-plugin-export

COPY pyproject.toml poetry.lock ./
RUN poetry export -f requirements.txt --without dev -o requirements.txt

COPY . .
RUN poetry build -f wheel

# --- Runtime stage ---
FROM python:3.11-slim
WORKDIR /app

COPY --from=builder /build/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && rm requirements.txt

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Copy runtime assets and data
COPY config/config.docker.yaml /app/config-defaults/config.yaml
COPY config/config.yaml.example /app/config-defaults/config.yaml.example
COPY data/ /app/data/
COPY assets/ /app/assets/
COPY docker-entrypoint.sh /app/

RUN chmod +x /app/docker-entrypoint.sh && \
    mkdir -p /app/output /app/storage /app/config

EXPOSE 47475

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://127.0.0.1:47475/health', timeout=3)" || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["flights", "service"]
