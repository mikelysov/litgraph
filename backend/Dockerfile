FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS base
WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Cache deps (but not project code)
COPY backend/pyproject.toml backend/uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# Final stage for CPU dev
FROM base AS cpu
WORKDIR /app
COPY backend/ /app/
RUN uv sync --frozen

ENV PYTHONUNBUFFERED=1
CMD ["uv", "run", "poe", "server"]

# Optional GPU stage
FROM cpu AS gpu
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /opt/venv/bin/python accelerate

ENV PYTHONUNBUFFERED=1
CMD ["uv", "run", "poe", "server"]