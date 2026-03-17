.PHONY: install sync lint format test test-all coverage clean docker-build docker-test notebook

# ---------------------------------------------------------------------------
# Environment — managed by uv
# ---------------------------------------------------------------------------

install:
	uv sync --all-extras

# Alias for muscle memory
sync: install

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------

lint:
	uv run ruff check src/ tests/
	uv run mypy src/polaris_re/

format:
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

# Run both lint and format in one pass (useful pre-commit)
check: format lint

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

test:
	uv run pytest -m "not slow" tests/

test-all:
	uv run pytest tests/

coverage:
	uv run pytest --cov=polaris_re --cov-report=term-missing --cov-report=html tests/
	@echo "HTML coverage report: htmlcov/index.html"

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

docker-build:
	docker build -t polaris-re:dev .

docker-test:
	docker run --rm polaris-re:dev python -m pytest tests/ -v --tb=short

docker-lint:
	docker run --rm polaris-re:dev python -m ruff check src/ tests/

# ---------------------------------------------------------------------------
# Notebooks
# ---------------------------------------------------------------------------

notebook:
	uv run jupyter lab notebooks/

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	find . -name "*.pyc" -delete
	find . -name ".coverage" -delete

# Validate that mortality table CSV files are present in $POLARIS_DATA_DIR
validate-tables:
	uv run python scripts/validate_tables.py

# Generate synthetic inforce block for dev/testing
synthetic-block:
	uv run python scripts/generate_synthetic_block.py --n-policies 5000
