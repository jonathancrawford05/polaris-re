"""Unit tests for the dashboard portfolio loader (Slice 1).

The loader is a thin wrapper around the CLI's portfolio config parser
(``polaris_re.cli._build_portfolio_from_config``) that gives the Streamlit
upload flow a clean Python-exception surface. These tests exercise both
entry points — load-from-disk and load-from-upload — and verify the error
paths the dashboard needs to render to the user.
"""

from pathlib import Path

import pytest

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.dashboard.components.portfolio_loader import (
    load_portfolio_from_config_path,
    load_portfolio_from_uploaded,
)

SAMPLE_DIR = Path(__file__).parent.parent.parent / "data" / "inputs" / "portfolio_sample"
SAMPLE_YAML = SAMPLE_DIR / "portfolio.yaml"

STAGGERED_DIR = (
    Path(__file__).parent.parent.parent / "data" / "inputs" / "portfolio_staggered_sample"
)
STAGGERED_YAML = STAGGERED_DIR / "portfolio.yaml"


@pytest.fixture()
def uploaded_payload() -> tuple[str, dict[str, bytes]]:
    """Read the on-disk sample as the shape an uploader produces.

    The YAML's ``inforce_csv`` keys reference ``data/inputs/portfolio_sample/...``
    paths; the loader is responsible for resolving them by basename to the
    uploaded CSV blobs.
    """
    yaml_text = SAMPLE_YAML.read_text()
    csv_files = {p.name: p.read_bytes() for p in SAMPLE_DIR.glob("*.csv")}
    return yaml_text, csv_files


class TestLoadFromConfigPath:
    def test_roundtrips_sample_portfolio(self) -> None:
        portfolio, hurdle = load_portfolio_from_config_path(SAMPLE_YAML)
        assert portfolio.n_deals == 4
        assert hurdle == pytest.approx(0.10)

    def test_sample_exercises_three_cedants(self) -> None:
        portfolio, _ = load_portfolio_from_config_path(SAMPLE_YAML)
        cedants = {d.cedant for d in portfolio.deals}
        assert len(cedants) >= 3, f"expected ≥3 cedants, got {cedants}"

    def test_missing_config_raises_validation(self, tmp_path: Path) -> None:
        with pytest.raises(PolarisValidationError):
            load_portfolio_from_config_path(tmp_path / "does_not_exist.yaml")

    def test_sample_resolves_block_valuation_date(self) -> None:
        """Every deal resolves to the CSVs' 2026-01-01 block date (ADR-074).

        The YAML sets no deal-level valuation_date, so the block-date
        fallback must fire — never date.today() — making the sample's
        numbers reproducible across run days.
        """
        from datetime import date

        portfolio, _ = load_portfolio_from_config_path(SAMPLE_YAML)
        resolved = {d.config.valuation_date for d in portfolio.deals}
        assert resolved == {date(2026, 1, 1)}


class TestLoadStaggeredSample:
    """The staggered-date sample (ADR-061 calendar-mode demo) loads and runs.

    Exercised here so the sample stays healthy even when the AppTest
    suite (tests/qa/test_dashboard_flows.py) is unavailable.
    """

    def test_roundtrips_staggered_portfolio(self) -> None:
        portfolio, hurdle = load_portfolio_from_config_path(STAGGERED_YAML)
        assert portfolio.n_deals == 4
        assert hurdle == pytest.approx(0.10)

    def test_calendar_run_produces_two_month_offsets(self) -> None:
        portfolio, hurdle = load_portfolio_from_config_path(STAGGERED_YAML)
        result = portfolio.run(hurdle, align="calendar")
        offsets = {dr.deal_id: dr.grid_offset for dr in result.deal_results}
        assert offsets == {"DEAL_A": 0, "DEAL_B": 0, "DEAL_C": 2, "DEAL_D": 2}
        # Grid origin is the earliest deal valuation date.
        assert result.aggregate_cash_flow.valuation_date.isoformat() == "2026-01-01"

    def test_strict_run_rejects_mixed_valuation_dates(self) -> None:
        portfolio, hurdle = load_portfolio_from_config_path(STAGGERED_YAML)
        with pytest.raises(PolarisValidationError, match="valuation date"):
            portfolio.run(hurdle, align="strict")


class TestLoadFromUploaded:
    def test_roundtrips_in_memory_yaml_and_csvs(
        self,
        uploaded_payload: tuple[str, dict[str, bytes]],
        tmp_path: Path,
    ) -> None:
        yaml_text, csv_files = uploaded_payload
        portfolio, hurdle = load_portfolio_from_uploaded(
            yaml_text=yaml_text,
            csv_files=csv_files,
            workdir=tmp_path,
        )
        assert portfolio.n_deals == 4
        assert hurdle == pytest.approx(0.10)

    def test_persists_files_to_workdir(
        self,
        uploaded_payload: tuple[str, dict[str, bytes]],
        tmp_path: Path,
    ) -> None:
        yaml_text, csv_files = uploaded_payload
        load_portfolio_from_uploaded(
            yaml_text=yaml_text,
            csv_files=csv_files,
            workdir=tmp_path,
        )
        for fname in csv_files:
            assert (tmp_path / fname).exists(), f"missing persisted CSV: {fname}"

    def test_creates_workdir_when_none(
        self,
        uploaded_payload: tuple[str, dict[str, bytes]],
    ) -> None:
        yaml_text, csv_files = uploaded_payload
        portfolio, _ = load_portfolio_from_uploaded(
            yaml_text=yaml_text,
            csv_files=csv_files,
        )
        assert portfolio.n_deals == 4

    def test_errors_on_missing_csv_reference(
        self,
        uploaded_payload: tuple[str, dict[str, bytes]],
        tmp_path: Path,
    ) -> None:
        yaml_text, csv_files = uploaded_payload
        # Drop one CSV from the upload set
        first = next(iter(csv_files))
        partial = {k: v for k, v in csv_files.items() if k != first}
        with pytest.raises(PolarisValidationError, match="inforce_csv"):
            load_portfolio_from_uploaded(
                yaml_text=yaml_text,
                csv_files=partial,
                workdir=tmp_path,
            )

    def test_errors_on_malformed_yaml(
        self,
        uploaded_payload: tuple[str, dict[str, bytes]],
        tmp_path: Path,
    ) -> None:
        _, csv_files = uploaded_payload
        bad_yaml = "deals: [unterminated"
        with pytest.raises(PolarisValidationError):
            load_portfolio_from_uploaded(
                yaml_text=bad_yaml,
                csv_files=csv_files,
                workdir=tmp_path,
            )

    def test_errors_on_non_mapping_yaml(
        self,
        uploaded_payload: tuple[str, dict[str, bytes]],
        tmp_path: Path,
    ) -> None:
        _, csv_files = uploaded_payload
        with pytest.raises(PolarisValidationError):
            load_portfolio_from_uploaded(
                yaml_text="- just\n- a\n- list\n",
                csv_files=csv_files,
                workdir=tmp_path,
            )
