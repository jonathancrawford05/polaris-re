"""QA test fixtures — golden inputs and shared constants.

The golden-regression machinery (config discovery, pricing, baseline I/O) lives
in ``golden_runner`` so the standalone ``generate_golden.py`` script can import
it without pulling in pytest. This conftest re-exports the constants the QA
tests reference and provides the pytest fixtures + the ``requires_soa_tables``
skip decorator.
"""

from pathlib import Path

import pytest

from polaris_re.core.pipeline import load_inforce

from .golden_runner import GOLDEN_CSV, GOLDEN_OUTPUTS_DIR, has_soa_tables

# Re-exported for the QA tests (test_cli_golden imports GOLDEN_CONFIGS_DIR /
# GOLDEN_CSV; test_pipeline_golden imports GOLDEN_OUTPUTS_DIR).
GOLDEN_CONFIGS_DIR = Path("data/qa")

__all__ = [
    "GOLDEN_CONFIGS_DIR",
    "GOLDEN_CSV",
    "GOLDEN_OUTPUTS_DIR",
    "requires_soa_tables",
]


def requires_soa_tables(fn):
    """Skip decorator for tests that need the real SOA VBT 2015 tables."""
    return pytest.mark.skipif(
        not has_soa_tables(),
        reason="SOA VBT 2015 tables not found (run scripts/convert_soa_tables.py)",
    )(fn)


@pytest.fixture()
def golden_inforce():
    """Load the golden inforce block."""
    if not GOLDEN_CSV.exists():
        pytest.skip(f"Golden CSV not found: {GOLDEN_CSV}")
    return load_inforce(csv_path=GOLDEN_CSV)
