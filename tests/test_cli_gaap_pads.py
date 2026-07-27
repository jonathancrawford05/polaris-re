"""Tests for the ``polaris price`` GAAP (FAS 60) PAD flags and config fields.

The two GAAP provisions for adverse deviation are built onto ``ProjectionConfig``
(ADR-127/128); this surfacing work threads them through the config parser
(``deal.gaap_mortality_pad`` / ``deal.gaap_interest_margin``) and the
``--gaap-mortality-pad`` / ``--gaap-interest-margin`` flags. These tests verify:

* omitting the PADs (or setting them neutral) is byte-identical to prior runs,
  with no PAD keys in the JSON summary;
* a non-neutral PAD on the GAAP basis moves the priced numbers and is echoed in
  the summary (the audit trail);
* the PADs are ignored on a non-GAAP basis (NET_PREMIUM byte-identical);
* the flag overrides the config field (flag-over-config precedence);
* the config field is honoured when no flag is supplied;
* an out-of-range value fails with a clean error.
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from polaris_re.cli import _build_pipeline_from_config, app

runner = CliRunner()

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


class TestGAAPPadFlags:
    def test_default_gaap_run_has_no_pad_keys(self, tmp_path: Path) -> None:
        """A GAAP run without PADs omits the PAD keys (byte-identical audit line)."""
        payload = _run_price(tmp_path, "--reserve-basis", "GAAP")
        assert "gaap_mortality_pad" not in payload["summary"]
        assert "gaap_interest_margin" not in payload["summary"]

    def test_explicit_neutral_pads_byte_identical(self, tmp_path: Path) -> None:
        """Neutral PADs (1.0 / 0.0) reproduce the default GAAP run exactly."""
        default = _run_price(tmp_path / "a", "--reserve-basis", "GAAP")
        explicit = _run_price(
            tmp_path / "b",
            "--reserve-basis",
            "GAAP",
            "--gaap-mortality-pad",
            "1.0",
            "--gaap-interest-margin",
            "0.0",
        )
        assert default == explicit

    def test_mortality_pad_changes_priced_numbers_and_echoes(self, tmp_path: Path) -> None:
        """A mortality PAD > 1.0 raises the GAAP reserve, moving profits; echoed."""
        neutral = _run_price(tmp_path / "a", "--reserve-basis", "GAAP")
        padded = _run_price(
            tmp_path / "b", "--reserve-basis", "GAAP", "--gaap-mortality-pad", "1.10"
        )
        assert padded["summary"]["gaap_mortality_pad"] == 1.10
        assert (
            abs(
                neutral["summary"]["total_pv_profits_cedant"]
                - padded["summary"]["total_pv_profits_cedant"]
            )
            > 1.0
        )

    def test_interest_margin_changes_priced_numbers_and_echoes(self, tmp_path: Path) -> None:
        """A positive interest margin lowers the GAAP discount rate, moving profits."""
        neutral = _run_price(tmp_path / "a", "--reserve-basis", "GAAP")
        padded = _run_price(
            tmp_path / "b", "--reserve-basis", "GAAP", "--gaap-interest-margin", "0.01"
        )
        assert padded["summary"]["gaap_interest_margin"] == 0.01
        assert (
            abs(
                neutral["summary"]["total_pv_profits_cedant"]
                - padded["summary"]["total_pv_profits_cedant"]
            )
            > 1.0
        )

    def test_pads_ignored_on_net_premium_basis(self, tmp_path: Path) -> None:
        """On NET_PREMIUM the PADs are ignored — a padded run equals the plain run."""
        plain = _run_price(tmp_path / "a")  # default basis is NET_PREMIUM
        padded = _run_price(
            tmp_path / "b", "--gaap-mortality-pad", "1.25", "--gaap-interest-margin", "0.02"
        )
        # The priced numbers are identical; only the echoed summary keys differ.
        assert (
            plain["summary"]["total_pv_profits_cedant"]
            == padded["summary"]["total_pv_profits_cedant"]
        )

    def test_below_one_mortality_pad_errors_cleanly(self, tmp_path: Path) -> None:
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
                "--gaap-mortality-pad",
                "0.9",
            ],
        )
        assert result.exit_code != 0
        assert "--gaap-mortality-pad must be >= 1.0" in result.stdout

    def test_out_of_range_interest_margin_errors_cleanly(self, tmp_path: Path) -> None:
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
                "--gaap-interest-margin",
                "1.5",
            ],
        )
        assert result.exit_code != 0
        assert "--gaap-interest-margin must be in [0, 1]" in result.stdout


class TestGAAPPadConfigField:
    def test_config_fields_honoured(self, tmp_path: Path) -> None:
        """``deal.gaap_mortality_pad`` / ``deal.gaap_interest_margin`` drive the config."""
        raw = json.loads(GOLDEN_CONFIG_FLAT.read_text())
        deal = raw.setdefault("deal", {})
        deal["gaap_mortality_pad"] = 1.20
        deal["gaap_interest_margin"] = 0.008
        cfg_path = tmp_path / "pad_cfg.json"
        cfg_path.write_text(json.dumps(raw))
        _inforce, _assumptions, config, inputs = _build_pipeline_from_config(cfg_path, GOLDEN_CSV)
        assert config.gaap_mortality_pad == 1.20
        assert config.gaap_interest_margin == 0.008
        assert inputs.deal.gaap_mortality_pad == 1.20

    def test_flag_overrides_config(self, tmp_path: Path) -> None:
        """An explicit flag override beats the config's PAD fields."""
        raw = json.loads(GOLDEN_CONFIG_FLAT.read_text())
        raw.setdefault("deal", {})["gaap_mortality_pad"] = 1.20
        cfg_path = tmp_path / "pad_cfg.json"
        cfg_path.write_text(json.dumps(raw))
        _inforce, _assumptions, config, _inputs = _build_pipeline_from_config(
            cfg_path, GOLDEN_CSV, gaap_mortality_pad_override=1.05
        )
        assert config.gaap_mortality_pad == 1.05

    def test_default_config_is_neutral(self) -> None:
        """A config with no PAD fields defaults to the neutral values."""
        _inforce, _assumptions, config, _inputs = _build_pipeline_from_config(
            GOLDEN_CONFIG_FLAT, GOLDEN_CSV
        )
        assert config.gaap_mortality_pad == 1.0
        assert config.gaap_interest_margin == 0.0
