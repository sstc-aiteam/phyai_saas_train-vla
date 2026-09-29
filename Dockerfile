# Backend API image, deployed to Cloud Run (spec section 2). Not to be
# confused with docker/act/ and docker/smolvla/, which build the training
# containers the *worker* runs on the GPU host — this one only ever runs
# `backend.main:app`, never `worker.main`.
FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# --frozen: fail instead of silently re-resolving if uv.lock is stale.
# --no-dev: skip pytest/pytest-mock/pytest-asyncio, not needed at runtime.
RUN uv sync --frozen --no-dev

RUN useradd --system --create-home appuser
USER appuser

ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

# Cloud Run injects $PORT (defaults to 8080) and expects the container to
# listen on it — never hardcode a port here.
EXPOSE 8080
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
