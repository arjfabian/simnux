FROM python:3.12-alpine AS builder

WORKDIR /app

RUN apk add --no-cache gcc musl-dev libffi-dev yaml-dev

# 1. Copy local contents (.) to /app/backend
COPY . /app/backend

RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip build && \
    /opt/venv/bin/pip install --no-cache-dir pyyaml /app/backend


FROM python:3.12-alpine AS runner

WORKDIR /app

RUN apk add --no-cache yaml

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=8001 \
    PYTHONPATH="/app/backend/src"

# 2. Copy local contents (.) to /app/backend
COPY . /app/backend

# 3. Clean up non-hello scenarios inside /app/backend/scenarios
RUN find /app/backend/scenarios -mindepth 1 -maxdepth 1 -type d ! -name "hello" -exec rm -rf {} +

RUN adduser -D simnux && \
    chown -R simnux:simnux /app

USER simnux

EXPOSE 8001

CMD ["uvicorn", "simnux.init.app_factory:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
