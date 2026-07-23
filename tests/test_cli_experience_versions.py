"""Tests for the ``polaris experience save`` / ``list`` CLI surface (A4' Slice 4b-2).

Exercises the versioned-persistence commands end-to-end through Typer's
``CliRunner``: an emitted CUSTOM improvement JSON is saved with study-date +
credibility provenance into an append-only store (a ``tmp_path`` root, never
``data/``), re-saving the same study date appends rather than overwrites, and
``list`` renders the stored history. All study dates are pinned literals
(ADR-074 guard).
"""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from polaris_re.assumptions.improvement import MortalityImprovement
from polaris_re.assumptions.version_store import (
    AssumptionVersionStore,
)
from polaris_re.cli import app

runner = CliRunner()

_AGES = np.arange(40, 46, dtype=np.int64)
_YEARS = np.arange(2016, 2021, dtype=np.int64)


def _write_custom_scale(path: Path, mi: float = 0.012) -> None:
    """Write a CUSTOM MortalityImprovement JSON (the `improvement --output` artifact)."""
    grid = np.full((_AGES.size, _YEARS.size), mi, dtype=np.float64)
    scale = MortalityImprovement.from_grid(_AGES, _YEARS, grid, ultimate_rate=0.01)
    path.write_text(scale.model_dump_json(indent=2), encoding="utf-8")


def test_save_persists_versioned_scale(tmp_path: Path) -> None:
    """`save` wraps the emitted scale with provenance and writes it to the store."""
    scale_json = tmp_path / "scale.json"
    store_dir = tmp_path / "store"
    _write_custom_scale(scale_json)

    result = runner.invoke(
        app,
        [
            "experience",
            "save",
            "-i",
            str(scale_json),
            "--study-date",
            "2024-12-31",
            "--credibility",
            "0.8",
            "--label",
            "term-block-A",
            "--store-dir",
            str(store_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "2024-12-31-001" in result.output

    version = AssumptionVersionStore(store_dir).load("2024-12-31-001")
    assert version.study_date == date(2024, 12, 31)
    assert version.credibility == pytest.approx(0.8)
    assert version.label == "term-block-A"


def test_save_is_append_only(tmp_path: Path) -> None:
    """Two saves of the same study date yield -001 and -002, both preserved."""
    scale_json = tmp_path / "scale.json"
    store_dir = tmp_path / "store"
    _write_custom_scale(scale_json, mi=0.010)

    r1 = runner.invoke(
        app,
        [
            "experience",
            "save",
            "-i",
            str(scale_json),
            "--study-date",
            "2024-12-31",
            "--store-dir",
            str(store_dir),
        ],
    )
    _write_custom_scale(scale_json, mi=0.020)
    r2 = runner.invoke(
        app,
        [
            "experience",
            "save",
            "-i",
            str(scale_json),
            "--study-date",
            "2024-12-31",
            "--store-dir",
            str(store_dir),
        ],
    )
    assert r1.exit_code == 0 and r2.exit_code == 0, (r1.output, r2.output)
    assert "2024-12-31-001" in r1.output
    assert "2024-12-31-002" in r2.output

    versions = AssumptionVersionStore(store_dir).list_versions()
    assert [v.version_id for v in versions] == ["2024-12-31-001", "2024-12-31-002"]


def test_list_renders_stored_versions(tmp_path: Path) -> None:
    """`list` reports each stored version's id, study date, and credibility."""
    scale_json = tmp_path / "scale.json"
    store_dir = tmp_path / "store"
    _write_custom_scale(scale_json)
    runner.invoke(
        app,
        [
            "experience",
            "save",
            "-i",
            str(scale_json),
            "--study-date",
            "2024-12-31",
            "--credibility",
            "0.65",
            "--store-dir",
            str(store_dir),
        ],
    )

    # Widen the (non-tty) console so the Rich table does not truncate columns.
    result = runner.invoke(
        app,
        ["experience", "list", "--store-dir", str(store_dir)],
        env={"COLUMNS": "200"},
    )
    assert result.exit_code == 0, result.output
    assert "2024-12-31-001" in result.output
    assert "0.65" in result.output


def test_list_empty_store(tmp_path: Path) -> None:
    """`list` on an empty store reports no versions (exit 0, not an error)."""
    result = runner.invoke(app, ["experience", "list", "--store-dir", str(tmp_path / "empty")])
    assert result.exit_code == 0, result.output
    assert "No assumption versions" in result.output


def test_save_rejects_non_custom_scale(tmp_path: Path) -> None:
    """A built-in (non-CUSTOM) scale JSON is rejected with a non-zero exit."""
    scale_json = tmp_path / "builtin.json"
    scale_json.write_text(json.dumps({"scale": "scale_aa", "base_year": 2015}), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "experience",
            "save",
            "-i",
            str(scale_json),
            "--study-date",
            "2024-12-31",
            "--store-dir",
            str(tmp_path / "store"),
        ],
    )
    assert result.exit_code == 1
    assert "CUSTOM" in result.output


def test_save_rejects_bad_study_date(tmp_path: Path) -> None:
    """A malformed study date exits with a clear error before any write."""
    scale_json = tmp_path / "scale.json"
    _write_custom_scale(scale_json)
    result = runner.invoke(
        app,
        [
            "experience",
            "save",
            "-i",
            str(scale_json),
            "--study-date",
            "12/31/2024",
            "--store-dir",
            str(tmp_path / "store"),
        ],
    )
    assert result.exit_code == 1
    assert "YYYY-MM-DD" in result.output


def test_save_missing_improvement_file(tmp_path: Path) -> None:
    """A missing improvement JSON exits with a clear error."""
    result = runner.invoke(
        app,
        [
            "experience",
            "save",
            "-i",
            str(tmp_path / "nope.json"),
            "--study-date",
            "2024-12-31",
            "--store-dir",
            str(tmp_path / "store"),
        ],
    )
    assert result.exit_code == 1
    assert "not found" in result.output
