"""Tests for the ``mortality.improvement_version_id`` config selector + flag.

A4' epic (Data-Driven Experience Analysis), Slice 4b-3 (ADR-148). Slice 4b-2
(ADR-147) added the append-only ``AssumptionVersionStore`` that freezes an
experience-derived ``ImprovementScale.CUSTOM`` ``MortalityImprovement`` with
study-date/credibility provenance. This slice wires that store into the pricing
``--config`` schema (``mortality.improvement_version_id`` +
``improvement_store_dir`` / ``improvement_kind``) and the ``--improvement-version``
CLI flag, via the ``build_assumption_set`` selector
(``load_improvement_version``), so a frozen, audited basis drives a
``polaris price`` run's best-estimate mortality.

These tests verify that:

* the ``build_assumption_set`` selector loads the versioned CUSTOM scale onto
  ``AssumptionSet.improvement`` and leaves it ``None`` (byte-identical) by
  default;
* an unknown version id raises ``PolarisValidationError``;
* ``default_store_root`` honours ``$POLARIS_DATA_DIR``;
* the CLI ``price`` run selects the version from the config field, echoes it in
  the summary only when set (no always-present ``null``), and the selected
  improvement actually reaches the engine (priced numbers move);
* the ``--improvement-version`` flag overrides the config field;
* an unknown version id from either surface exits non-zero.

The engine's *application* of an improvement scale (lower best-estimate q →
lower claims) is already pinned by ``tests/test_products/test_wl_improvement.py``
and the TermLife improvement path; here we prove only that the config/flag
wiring delivers the frozen scale into the priced run.
"""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from polaris_re.assumptions.improvement import ImprovementScale, MortalityImprovement
from polaris_re.assumptions.version_store import (
    DEFAULT_ASSUMPTION_KIND,
    AssumptionVersionStore,
    default_store_root,
)
from polaris_re.cli import app
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.pipeline import (
    MortalityConfig,
    PipelineInputs,
    build_assumption_set,
    load_improvement_version,
)

runner = CliRunner()

GOLDEN_DIR = Path("data/qa")
GOLDEN_CSV = GOLDEN_DIR / "golden_inforce.csv"
GOLDEN_CONFIG_FLAT = GOLDEN_DIR / "golden_config_flat.json"


def _make_custom_scale(mi_rate: float = 0.02) -> MortalityImprovement:
    """A CUSTOM improvement scale: constant ``mi_rate`` over 2026-2030, ages 30-90.

    The grid spans the golden config's projection calendar years (valuation
    2026-04-01) and its attained-age range, so the scale bites on every priced
    cohort. Ages/years are pinned (never the wall clock) per the ADR-074 guard.
    """
    ages = np.arange(30, 91, dtype=np.int32)
    years = np.arange(2026, 2031, dtype=np.int32)
    grid = np.full((len(ages), len(years)), mi_rate, dtype=np.float64)
    return MortalityImprovement.from_grid(ages, years, grid, ultimate_rate=mi_rate)


def _save_version(
    store_dir: Path,
    *,
    mi_rate: float = 0.02,
    kind: str = DEFAULT_ASSUMPTION_KIND,
) -> str:
    """Persist a CUSTOM scale to ``store_dir`` and return its version id."""
    store = AssumptionVersionStore(store_dir)
    version = store.save(
        _make_custom_scale(mi_rate),
        date(2024, 12, 31),
        credibility=0.8,
        label="test",
        kind=kind,
    )
    return version.version_id


def _write_config_with_improvement(
    tmp_path: Path,
    store_dir: Path,
    version_id: str,
    *,
    kind: str | None = None,
) -> Path:
    """Copy the golden flat config, inject the improvement selector, write it out."""
    raw = json.loads(GOLDEN_CONFIG_FLAT.read_text())
    raw["mortality"]["improvement_version_id"] = version_id
    raw["mortality"]["improvement_store_dir"] = str(store_dir)
    if kind is not None:
        raw["mortality"]["improvement_kind"] = kind
    cfg_path = tmp_path / "config_with_improvement.json"
    cfg_path.write_text(json.dumps(raw))
    return cfg_path


def _run_price(config_path: Path, out: Path, *extra_args: str) -> dict:  # type: ignore[type-arg]
    """Invoke ``polaris price`` on ``config_path``; assert success; return payload."""
    result = runner.invoke(
        app,
        [
            "price",
            "--config",
            str(config_path),
            "--inforce",
            str(GOLDEN_CSV),
            "--output",
            str(out),
            *extra_args,
        ],
    )
    assert result.exit_code == 0, f"CLI failed:\n{result.stdout}"
    return json.loads(out.read_text())  # type: ignore[no-any-return]


# --------------------------------------------------------------------------- #
# Selector / build_assumption_set (pipeline level)                            #
# --------------------------------------------------------------------------- #


class TestSelector:
    def test_load_improvement_version_roundtrips(self, tmp_path: Path) -> None:
        """The selector returns the same CUSTOM grid that was saved."""
        saved = _make_custom_scale(0.015)
        store = AssumptionVersionStore(tmp_path)
        vid = store.save(saved, date(2024, 12, 31)).version_id

        loaded = load_improvement_version(vid, store_dir=tmp_path)

        assert loaded.scale is ImprovementScale.CUSTOM
        assert loaded.custom_ages == saved.custom_ages
        assert loaded.custom_years == saved.custom_years
        assert loaded.custom_mi_grid == saved.custom_mi_grid

    def test_load_improvement_version_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(PolarisValidationError):
            load_improvement_version("2024-12-31-999", store_dir=tmp_path)

    def test_load_improvement_version_honours_kind(self, tmp_path: Path) -> None:
        """A version filed under a non-default kind is found only under that kind."""
        vid = _save_version(tmp_path, kind="segment_improvement")
        loaded = load_improvement_version(vid, store_dir=tmp_path, kind="segment_improvement")
        assert loaded.scale is ImprovementScale.CUSTOM
        with pytest.raises(PolarisValidationError):
            load_improvement_version(vid, store_dir=tmp_path)  # default kind → absent

    def test_default_store_root_honours_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POLARIS_DATA_DIR", "/tmp/polaris-xyz")
        assert default_store_root() == Path("/tmp/polaris-xyz") / "assumption_versions"
        monkeypatch.delenv("POLARIS_DATA_DIR", raising=False)
        assert default_store_root() == Path("data") / "assumption_versions"


class TestBuildAssumptionSet:
    def test_default_leaves_improvement_none(self) -> None:
        """No version id → AssumptionSet.improvement stays None (byte-identical)."""
        aset = build_assumption_set(
            PipelineInputs(mortality=MortalityConfig(source="flat", flat_qx=0.01))
        )
        assert aset.improvement is None

    def test_selects_versioned_scale(self, tmp_path: Path) -> None:
        """A referenced version id threads the frozen CUSTOM scale onto the set."""
        vid = _save_version(tmp_path)
        aset = build_assumption_set(
            PipelineInputs(
                mortality=MortalityConfig(
                    source="flat",
                    flat_qx=0.01,
                    improvement_version_id=vid,
                    improvement_store_dir=tmp_path,
                )
            )
        )
        assert aset.improvement is not None
        assert aset.improvement.scale is ImprovementScale.CUSTOM
        assert aset.improvement.custom_years == _make_custom_scale().custom_years

    def test_unknown_version_raises(self, tmp_path: Path) -> None:
        with pytest.raises(PolarisValidationError):
            build_assumption_set(
                PipelineInputs(
                    mortality=MortalityConfig(
                        source="flat",
                        flat_qx=0.01,
                        improvement_version_id="2024-12-31-999",
                        improvement_store_dir=tmp_path,
                    )
                )
            )


# --------------------------------------------------------------------------- #
# CLI wiring (config field + flag)                                            #
# --------------------------------------------------------------------------- #


class TestCliWiring:
    def test_default_omits_summary_key(self, tmp_path: Path) -> None:
        """No selector → the summary omits the key entirely (byte-identical)."""
        payload = _run_price(GOLDEN_CONFIG_FLAT, tmp_path / "base.json")
        assert "mortality_improvement_version" not in payload["summary"]

    def test_config_field_selects_and_echoes(self, tmp_path: Path) -> None:
        """The config field drives the run and is echoed in the summary."""
        store_dir = tmp_path / "store"
        vid = _save_version(store_dir)
        cfg = _write_config_with_improvement(tmp_path, store_dir, vid)

        payload = _run_price(cfg, tmp_path / "improved.json")

        assert payload["summary"]["mortality_improvement_version"] == vid

    def test_selected_improvement_reaches_engine(self, tmp_path: Path) -> None:
        """The frozen scale actually moves priced numbers vs the baseline run.

        A positive mortality improvement lowers best-estimate q over the
        projection, so the priced cedant PV differs from the no-improvement
        baseline — proof the wiring reaches the product engine rather than being
        dropped between config and AssumptionSet.
        """
        base = _run_price(GOLDEN_CONFIG_FLAT, tmp_path / "base.json")

        store_dir = tmp_path / "store"
        vid = _save_version(store_dir, mi_rate=0.05)
        cfg = _write_config_with_improvement(tmp_path, store_dir, vid)
        improved = _run_price(cfg, tmp_path / "improved.json")

        base_pv = base["summary"]["total_pv_profits_cedant"]
        improved_pv = improved["summary"]["total_pv_profits_cedant"]
        assert improved_pv != pytest.approx(base_pv), (
            "improvement selector did not change priced output — wiring dropped it"
        )

    def test_flag_overrides_config_field(self, tmp_path: Path) -> None:
        """``--improvement-version`` beats ``mortality.improvement_version_id``."""
        store_dir = tmp_path / "store"
        cfg_vid = _save_version(store_dir, mi_rate=0.02)  # 2024-12-31-001
        flag_vid = _save_version(store_dir, mi_rate=0.06)  # 2024-12-31-002
        assert cfg_vid != flag_vid
        cfg = _write_config_with_improvement(tmp_path, store_dir, cfg_vid)

        payload = _run_price(cfg, tmp_path / "flag.json", "--improvement-version", flag_vid)
        assert payload["summary"]["mortality_improvement_version"] == flag_vid

    def test_unknown_version_id_exits_nonzero(self, tmp_path: Path) -> None:
        store_dir = tmp_path / "store"
        _save_version(store_dir)  # a real store, but ask for a missing id
        cfg = _write_config_with_improvement(tmp_path, store_dir, "2024-12-31-999")
        result = runner.invoke(
            app,
            [
                "price",
                "--config",
                str(cfg),
                "--inforce",
                str(GOLDEN_CSV),
                "--output",
                str(tmp_path / "nope.json"),
            ],
        )
        assert result.exit_code != 0
