"""Tests for the ``polaris price --reserve-basis`` selector (reserve-basis epic, slice 4).

Slice 4 surfaces the ``ReserveBasis`` selector (built into ``ProjectionConfig``
in slice 1 and given concrete CRVM / VM20 bases in slices 2-3) on the CLI. These
tests verify that:

* the default path is byte-identical (NET_PREMIUM), with the basis echoed in the
  JSON summary;
* a non-default basis flows through to the priced numbers;
* the flag overrides a ``reserve_basis`` set in the config (flag-over-config
  precedence, matching the YRT-rate-table surfaces);
* an unknown basis fails with a clean error and the list of valid values;
* the config ``deal.reserve_basis`` field is honoured when no flag is supplied.
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from polaris_re.cli import _build_pipeline_from_config, app
from polaris_re.core.reserve_basis import ReserveBasis

runner = CliRunner()

# Golden fixtures live under data/qa (see tests/qa/conftest.py), referenced
# relative to the repo root — the pytest invocation cwd.
GOLDEN_DIR = Path("data/qa")
GOLDEN_CSV = GOLDEN_DIR / "golden_inforce.csv"
GOLDEN_CONFIG_FLAT = GOLDEN_DIR / "golden_config_flat.json"


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


class TestReserveBasisFlag:
    def test_default_summary_reports_net_premium(self, tmp_path: Path) -> None:
        """With no flag, the summary echoes NET_PREMIUM (the default basis)."""
        payload = _run_price(tmp_path)
        assert payload["summary"]["reserve_basis"] == "NET_PREMIUM"

    def test_explicit_net_premium_byte_identical_to_default(self, tmp_path: Path) -> None:
        """``--reserve-basis NET_PREMIUM`` produces the same numbers as the default."""
        default = _run_price(tmp_path / "a")
        explicit = _run_price(tmp_path / "b", "--reserve-basis", "NET_PREMIUM")
        assert default == explicit

    def test_crvm_changes_priced_numbers(self, tmp_path: Path) -> None:
        """A non-default basis moves the reserve and therefore the profit numbers."""
        net = _run_price(tmp_path / "a")
        crvm = _run_price(tmp_path / "b", "--reserve-basis", "CRVM")
        assert crvm["summary"]["reserve_basis"] == "CRVM"
        # The whole-life cohort's reserve changes materially under CRVM.
        net_by_pt = {c["product_type"]: c for c in net["cohorts"]}
        crvm_by_pt = {c["product_type"]: c for c in crvm["cohorts"]}
        wl_net = net_by_pt["WHOLE_LIFE"]["cedant"]["pv_profits"]
        wl_crvm = crvm_by_pt["WHOLE_LIFE"]["cedant"]["pv_profits"]
        assert abs(wl_net - wl_crvm) > 1.0

    def test_lowercase_basis_accepted(self, tmp_path: Path) -> None:
        """The flag is case-insensitive (``crvm`` resolves to CRVM)."""
        payload = _run_price(tmp_path, "--reserve-basis", "crvm")
        assert payload["summary"]["reserve_basis"] == "CRVM"

    def test_unknown_basis_errors_cleanly(self, tmp_path: Path) -> None:
        """An unknown basis exits non-zero with the list of valid values."""
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
                "BOGUS",
            ],
        )
        assert result.exit_code != 0
        assert "Unknown --reserve-basis" in result.stdout
        assert "NET_PREMIUM" in result.stdout


class TestReserveBasisConfigField:
    def test_config_field_honoured(self, tmp_path: Path) -> None:
        """``deal.reserve_basis`` in the config drives the ProjectionConfig basis."""
        raw = json.loads(GOLDEN_CONFIG_FLAT.read_text())
        raw.setdefault("deal", {})["reserve_basis"] = "CRVM"
        cfg_path = tmp_path / "rb_cfg.json"
        cfg_path.write_text(json.dumps(raw))
        _inforce, _assumptions, config, inputs = _build_pipeline_from_config(cfg_path, GOLDEN_CSV)
        assert config.reserve_basis == ReserveBasis.CRVM
        assert inputs.deal.reserve_basis == "CRVM"

    def test_flag_overrides_config(self, tmp_path: Path) -> None:
        """An explicit override beats ``deal.reserve_basis`` in the config."""
        raw = json.loads(GOLDEN_CONFIG_FLAT.read_text())
        raw.setdefault("deal", {})["reserve_basis"] = "CRVM"
        cfg_path = tmp_path / "rb_cfg.json"
        cfg_path.write_text(json.dumps(raw))
        _inforce, _assumptions, config, _inputs = _build_pipeline_from_config(
            cfg_path, GOLDEN_CSV, reserve_basis_override="NET_PREMIUM"
        )
        assert config.reserve_basis == ReserveBasis.NET_PREMIUM

    def test_default_config_is_net_premium(self) -> None:
        """A config with no reserve_basis defaults to NET_PREMIUM."""
        _inforce, _assumptions, config, _inputs = _build_pipeline_from_config(
            GOLDEN_CONFIG_FLAT, GOLDEN_CSV
        )
        assert config.reserve_basis == ReserveBasis.NET_PREMIUM
