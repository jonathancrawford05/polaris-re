"""Tests for the ``polaris price --valuation-mortality`` selector.

Reserve-Basis Exactness epic, Slice 2 (surfacing). Slice 1 (ADR-125) added
``AssumptionSet.valuation_mortality`` so CRVM / the VM-20 NPR floor can value on
a prescribed statutory table; this slice surfaces it on the CLI (flag +
``deal.valuation_mortality`` config field). These tests verify that:

* the default path carries no ``valuation_mortality`` summary key (byte-identical
  output — no always-present ``null``);
* the flag is echoed in the JSON summary when set;
* CRVM valued on the prescribed 2001 CSO table produces different priced numbers
  than CRVM on the projection best-estimate table;
* ``NET_PREMIUM`` ignores the slot (historical pricing basis);
* the flag overrides ``deal.valuation_mortality`` in the config;
* the config field is honoured when no flag is supplied;
* an unknown source id fails (non-zero exit).

The golden flat config prices a TERM + WHOLE_LIFE block on a synthetic flat
projection table, so the CRVM-on-CSO difference is exercised on the WL cohort.
Tests that load the real 2001 CSO CSVs are skipped when those files are absent.
"""

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from polaris_re.cli import _build_pipeline_from_config, app

runner = CliRunner()

GOLDEN_DIR = Path("data/qa")
GOLDEN_CSV = GOLDEN_DIR / "golden_inforce.csv"
GOLDEN_CONFIG_FLAT = GOLDEN_DIR / "golden_config_flat.json"

_MORTALITY_DIR = Path(os.environ.get("POLARIS_DATA_DIR", "data")) / "mortality_tables"
_HAS_CSO = (_MORTALITY_DIR / "cso_2001_male.csv").exists()
requires_cso = pytest.mark.skipif(
    not _HAS_CSO, reason="2001 CSO tables required (run scripts/convert_soa_tables.py)"
)


def _run_price(tmp_path: Path, *extra_args: str) -> dict:  # type: ignore[type-arg]
    """Invoke ``polaris price`` on the flat golden config; return the JSON payload."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    out = tmp_path / "result.json"
    result = runner.invoke(
        app,
        [
            "price",
            "--config",
            str(GOLDEN_CONFIG_FLAT),
            "--inforce",
            str(GOLDEN_CSV),
            "--output",
            str(out),
            *extra_args,
        ],
    )
    assert result.exit_code == 0, f"CLI failed:\n{result.stdout}"
    return json.loads(out.read_text())  # type: ignore[no-any-return]


def _wl_pv(payload: dict) -> float:  # type: ignore[type-arg]
    by_pt = {c["product_type"]: c for c in payload["cohorts"]}
    return by_pt["WHOLE_LIFE"]["cedant"]["pv_profits"]  # type: ignore[no-any-return]


class TestValuationMortalityFlag:
    def test_default_has_no_valuation_mortality_key(self, tmp_path: Path) -> None:
        """With no flag, the summary omits the key entirely (byte-identical)."""
        payload = _run_price(tmp_path)
        assert "valuation_mortality" not in payload["summary"]

    @requires_cso
    def test_flag_echoed_in_summary(self, tmp_path: Path) -> None:
        payload = _run_price(
            tmp_path, "--reserve-basis", "CRVM", "--valuation-mortality", "CSO_2001"
        )
        assert payload["summary"]["valuation_mortality"] == "CSO_2001"

    @requires_cso
    def test_crvm_on_cso_differs_from_crvm_on_projection_table(self, tmp_path: Path) -> None:
        """CRVM on the prescribed 2001 CSO table moves the WL reserve vs the
        projection best-estimate table."""
        crvm = _run_price(tmp_path / "a", "--reserve-basis", "CRVM")
        crvm_cso = _run_price(
            tmp_path / "b", "--reserve-basis", "CRVM", "--valuation-mortality", "CSO_2001"
        )
        assert abs(_wl_pv(crvm) - _wl_pv(crvm_cso)) > 1.0

    @requires_cso
    def test_net_premium_ignores_the_slot(self, tmp_path: Path) -> None:
        """NET_PREMIUM never values on the prescribed table — priced numbers are
        unchanged whether or not ``--valuation-mortality`` is supplied."""
        plain = _run_price(tmp_path / "a")
        with_slot = _run_price(tmp_path / "b", "--valuation-mortality", "CSO_2001")
        # The prescribed-table echo is the only permitted difference; the priced
        # numbers must be identical on the default NET_PREMIUM basis.
        assert _wl_pv(plain) == _wl_pv(with_slot)
        by_pt_a = {c["product_type"]: c for c in plain["cohorts"]}
        by_pt_b = {c["product_type"]: c for c in with_slot["cohorts"]}
        assert by_pt_a["TERM"]["cedant"]["pv_profits"] == by_pt_b["TERM"]["cedant"]["pv_profits"]

    def test_unknown_source_errors(self, tmp_path: Path) -> None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        out = tmp_path / "result.json"
        result = runner.invoke(
            app,
            [
                "price",
                "--config",
                str(GOLDEN_CONFIG_FLAT),
                "--inforce",
                str(GOLDEN_CSV),
                "--output",
                str(out),
                "--reserve-basis",
                "CRVM",
                "--valuation-mortality",
                "BOGUS_TABLE",
            ],
        )
        assert result.exit_code != 0


class TestValuationMortalityConfigField:
    @requires_cso
    def test_config_field_honoured(self, tmp_path: Path) -> None:
        """``deal.valuation_mortality`` drives the AssumptionSet valuation table."""
        raw = json.loads(GOLDEN_CONFIG_FLAT.read_text())
        deal = raw.setdefault("deal", {})
        deal["reserve_basis"] = "CRVM"
        deal["valuation_mortality"] = "CSO_2001"
        cfg_path = tmp_path / "cfg.json"
        cfg_path.write_text(json.dumps(raw))
        _inf, assumptions, _cfg, inputs = _build_pipeline_from_config(cfg_path, GOLDEN_CSV)
        assert inputs.deal.valuation_mortality == "CSO_2001"
        assert assumptions.valuation_mortality is not None
        assert assumptions.valuation_mortality.source.value == "CSO_2001"

    @requires_cso
    def test_flag_overrides_config(self, tmp_path: Path) -> None:
        raw = json.loads(GOLDEN_CONFIG_FLAT.read_text())
        raw.setdefault("deal", {})["valuation_mortality"] = "CSO_2001"
        cfg_path = tmp_path / "cfg.json"
        cfg_path.write_text(json.dumps(raw))
        _inf, assumptions, _cfg, inputs = _build_pipeline_from_config(
            cfg_path, GOLDEN_CSV, valuation_mortality_override="flat"
        )
        assert inputs.deal.valuation_mortality == "flat"
        # The flag-loaded synthetic flat table, not the config's CSO_2001.
        assert assumptions.valuation_mortality is not None
        assert assumptions.valuation_mortality.table_name.startswith("Flat Rate")

    def test_default_config_has_no_valuation_mortality(self) -> None:
        _inf, assumptions, _cfg, inputs = _build_pipeline_from_config(
            GOLDEN_CONFIG_FLAT, GOLDEN_CSV
        )
        assert inputs.deal.valuation_mortality is None
        assert assumptions.valuation_mortality is None
