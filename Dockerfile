# =============================================================================
# Polaris RE — Multi-stage Docker build
# =============================================================================
# Stages:
#   builder  — installs uv, resolves and installs all dependencies
#   runtime  — minimal image for production / CI test runs
#   dev      — extends runtime with dev tools (Jupyter, pytest, mypy, ruff)
#
# Usage:
#   docker build -t polaris-re:dev --target dev .
#   docker build -t polaris-re:prod .
#   docker run --rm polaris-re:dev uv run pytest tests/
#   docker compose run --rm dev bash
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1 — Builder: install uv and resolve all dependencies
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency manifests first (maximise Docker layer caching)
COPY pyproject.toml ./
COPY uv.lock* ./

# Install all extras into /app/.venv
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
RUN uv sync --frozen --no-install-project --extra dev

# Install the project itself
COPY src/ ./src/
RUN uv sync --frozen --extra dev

# ---------------------------------------------------------------------------
# Stage 2 — Runtime: minimal production / CI image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

COPY tests/ ./tests/
COPY scripts/ ./scripts/
COPY pyproject.toml ./
COPY Makefile ./
COPY .env.example ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POLARIS_DATA_DIR=/data

RUN mkdir -p /data

# Smoke test
RUN python -c "import polaris_re; print(f'polaris_re {polaris_re.__version__} OK')"

CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]

# ---------------------------------------------------------------------------
# Stage 3 — Dev: runtime + Jupyter + full dev tooling
# ---------------------------------------------------------------------------
FROM runtime AS dev

# Copy notebooks for JupyterLab
COPY notebooks/ ./notebooks/

# Install Jupyter and dev extras (already in .venv from builder)
# No extra install needed — all extras were installed in builder stage

# Expose JupyterLab port
EXPOSE 8888

# Default dev command: interactive pytest
CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short", "-m", "not slow"]
