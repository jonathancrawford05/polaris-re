"""QA test fixtures — golden inputs and pipeline builders."""

import os
from datetime import date
from pathlib import Path

import pytest

from polaris_re.core.pipeline import (
    DealConfig,
    LapseConfig,
    MortalityConfig,
    PipelineInputs,
    load_inforce,
)

GOLDEN_CSV = Path("data/qa/golden_inforce.csv")
GOLDEN_CONFIGS_DIR = Path("data/qa")
GOLDEN_OUTPUTS_DIR = Path("tests/qa/golden_outputs")

# Mortality tables required for SOA VBT 2015 configs
_MORTALITY_DIR = Path(os.environ.get("POLARIS_DATA_DIR", "data")) / "mortality_tables"
_HAS_SOA_TABLES = (_MORTALITY_DIR / "soa_vbt_2015_male_nonsmoker.csv").exists()


def requires_soa_tables(fn):
    """Skip decorator for tests that need real mortality tables."""
    return pytest.mark.skipif(
        not _HAS_SOA_TABLES,
        reason=f"SOA VBT 2015 tables not found at {_MORTALITY_DIR}",
    )(fn)


@pytest.fixture()
def golden_inforce():
    """Load the golden inforce block."""
    if not GOLDEN_CSV.exists():
        pytest.skip(f"Golden CSV not found: {GOLDEN_CSV}")
    return load_inforce(csv_path=GOLDEN_CSV)


@pytest.fixture()
def golden_yrt_inputs() -> PipelineInputs:
    """PipelineInputs matching golden_config_yrt.json."""
    return PipelineInputs(
        mortality=MortalityConfig(source="SOA_VBT_2015", multiplier=1.0),
        lapse=LapseConfig(),
        deal=DealConfig(
            product_type="TERM",
            treaty_type="YRT",
            cession_pct=0.90,
            yrt_loading=0.10,
            discount_rate=0.06,
            hurdle_rate=0.10,
            projection_years=20,
            valuation_date=date(2026, 4, 1),
        ),
    )


@pytest.fixture()
def golden_flat_inputs() -> PipelineInputs:
    """PipelineInputs matching golden_config_flat.json (no SOA tables)."""
    return PipelineInputs(
        mortality=MortalityConfig(source="flat", flat_qx=0.003),
        lapse=LapseConfig(),
        deal=DealConfig(
            product_type="TERM",
            treaty_type="YRT",
            cession_pct=0.90,
            yrt_loading=0.10,
            discount_rate=0.06,
            hurdle_rate=0.10,
            projection_years=20,
            valuation_date=date(2026, 4, 1),
        ),
    )
