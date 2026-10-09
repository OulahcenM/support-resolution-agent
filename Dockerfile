# syntax=docker/dockerfile:1

# ---------- Build stage: resolve dependencies with uv ----------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies first (cached layer — only rebuilt when the lockfile changes)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# ---------- Runtime stage: slim, non-root ----------
FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

WORKDIR /app
COPY --from=builder --chown=app:app /app /app
COPY --chown=app:app data/knowledge_base ./data/knowledge_base
COPY --chown=app:app ui ./ui
COPY --chown=app:app .streamlit ./.streamlit
RUN mkdir -p /app/var && chown app:app /app/var

USER app
EXPOSE 8000 8501

CMD ["uvicorn", "support_agent.api.main:app", "--host", "0.0.0.0", "--port", "8000"]