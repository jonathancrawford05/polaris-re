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
RUN uv sync --frozen --no-install-project --all-extras

# Install the project itself (hatchling needs README.md to build)
COPY src/ ./src/
COPY README.md ./
RUN uv sync --frozen --all-extras

# ---------------------------------------------------------------------------
# Stage 2 — Runtime: minimal production / CI image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

COPY tests/ ./tests/
COPY scripts/ ./scripts/
# deploy/ manifests are parsed by tests/test_deploy/ (ROADMAP 6.2 Slice 3); the
# runtime image runs the test suite, so they must be present in the image.
COPY deploy/ ./deploy/
# CI workflow YAML is parsed by tests/test_ci/ (perf-harness Slice 3, ADR-176) —
# same reason: the runtime image runs the test suite. Only the workflows dir is
# shipped (the rest of .github/ stays out via .dockerignore).
COPY .github/workflows/ ./.github/workflows/
COPY data/qa/ ./data/qa/
COPY data/validation/ ./data/validation/
COPY data/inputs/portfolio_sample/ ./data/inputs/portfolio_sample/
COPY data/inputs/portfolio_staggered_sample/ ./data/inputs/portfolio_staggered_sample/
COPY pyproject.toml ./
COPY Makefile ./
COPY .env.example ./
# Committed project-scope MCP config (ADR-171); tests/test_mcp/ asserts it names
# the polaris-mcp command, and the runtime image runs the test suite.
COPY .mcp.json ./
# Committed diligence findings (ADR-182). The experience-GAM notebook re-derives
# every quantitative claim in docs/MEASUREMENT_experience_gam_*.md from these
# reports and asserts it, so tests/test_notebooks/ needs them present. Findings
# only — aggregate statistics, never the licensed HMD/SOA source files. The rest
# of docs/ stays out via .dockerignore.
COPY docs/measurements/ ./docs/measurements/
# Attribution for the data behind those findings (ADR-183), asserted by
# tests/test_docs/test_data_attribution.py — and independently the right thing to
# ship alongside another party's experience data.
COPY docs/DATA_LICENSING.md ./docs/
COPY docs/MEASUREMENT_experience_gam_hmd.md docs/MEASUREMENT_experience_gam_ilec.md ./docs/

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
