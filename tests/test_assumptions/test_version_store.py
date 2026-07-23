"""Tests for the append-only assumption version store (A4' Slice 4b-2).

Exercises :class:`AssumptionVersionStore` and :class:`AssumptionVersion`: a
data-driven ``ImprovementScale.CUSTOM`` scale is wrapped with study-date +
credibility provenance, persisted append-only under ``{root}/{kind}/``, and
round-trips through JSON. All study dates are pinned literals (ADR-074 guard) —
no test reads the wall clock, and the store allocates ids from the study date
and a sequence counter, so behaviour is deterministic.
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.assumptions.improvement import ImprovementScale, MortalityImprovement
from polaris_re.assumptions.version_store import (
    DEFAULT_ASSUMPTION_KIND,
    AssumptionVersion,
    AssumptionVersionStore,
)
from polaris_re.core.exceptions import PolarisValidationError

_AGES = np.arange(40, 46, dtype=np.int64)
_YEARS = np.arange(2016, 2021, dtype=np.int64)


def _custom_scale(mi: float = 0.012, ultimate_rate: float = 0.01) -> MortalityImprovement:
    """A small CUSTOM improvement scale (flat MI) built via ``from_grid``."""
    grid = np.full((_AGES.size, _YEARS.size), mi, dtype=np.float64)
    return MortalityImprovement.from_grid(_AGES, _YEARS, grid, ultimate_rate=ultimate_rate)


def _builtin_scale() -> MortalityImprovement:
    """A non-CUSTOM scale (rejected by the store)."""
    return MortalityImprovement(scale=ImprovementScale.SCALE_AA, base_year=2015)


# --------------------------------------------------------------------------- #
# AssumptionVersion record contract
# --------------------------------------------------------------------------- #


def test_version_round_trips_through_json() -> None:
    """A version serialises and re-validates to an identical record."""
    version = AssumptionVersion(
        version_id="2024-12-31-001",
        study_date=date(2024, 12, 31),
        credibility=0.8,
        label="term-block-A",
        notes="ILEC 2016-2020 extract",
        improvement=_custom_scale(),
    )
    restored = AssumptionVersion.model_validate_json(version.model_dump_json())
    assert restored == version
    assert restored.improvement.scale is ImprovementScale.CUSTOM


def test_credibility_out_of_range_rejected() -> None:
    """Credibility must be a weight in [0, 1]."""
    with pytest.raises(PolarisValidationError):
        AssumptionVersion(
            version_id="2024-12-31-001",
            study_date=date(2024, 12, 31),
            credibility=1.5,
            improvement=_custom_scale(),
        )


def test_non_custom_scale_rejected() -> None:
    """The store persists experience-derived CUSTOM scales only."""
    with pytest.raises(PolarisValidationError):
        AssumptionVersion(
            version_id="2024-12-31-001",
            study_date=date(2024, 12, 31),
            improvement=_builtin_scale(),
        )


def test_credibility_optional() -> None:
    """Credibility and the free-form tags are optional."""
    version = AssumptionVersion(
        version_id="2024-12-31-001",
        study_date=date(2024, 12, 31),
        improvement=_custom_scale(),
    )
    assert version.credibility is None
    assert version.label is None
    assert version.kind == DEFAULT_ASSUMPTION_KIND


# --------------------------------------------------------------------------- #
# Store: save / load / list
# --------------------------------------------------------------------------- #


def test_save_allocates_id_and_writes_file(tmp_path: Path) -> None:
    """The first save for a study date allocates sequence 001 and writes JSON."""
    store = AssumptionVersionStore(tmp_path)
    version = store.save(_custom_scale(), date(2024, 12, 31), credibility=0.75)

    assert version.version_id == "2024-12-31-001"
    path = tmp_path / DEFAULT_ASSUMPTION_KIND / "2024-12-31-001.json"
    assert path.is_file()
    assert store.load("2024-12-31-001") == version


def test_save_is_append_only_for_same_study_date(tmp_path: Path) -> None:
    """Re-saving the same study date allocates a new sequence, never overwrites."""
    store = AssumptionVersionStore(tmp_path)
    v1 = store.save(_custom_scale(mi=0.010), date(2024, 12, 31))
    v2 = store.save(_custom_scale(mi=0.020), date(2024, 12, 31))

    assert v1.version_id == "2024-12-31-001"
    assert v2.version_id == "2024-12-31-002"
    # Both files survive — the earlier basis is preserved for audit.
    assert store.load("2024-12-31-001").improvement.custom_mi_grid[0][0] == pytest.approx(0.010)
    assert store.load("2024-12-31-002").improvement.custom_mi_grid[0][0] == pytest.approx(0.020)


def test_sequences_are_per_study_date(tmp_path: Path) -> None:
    """Sequence allocation is scoped to each study date."""
    store = AssumptionVersionStore(tmp_path)
    a = store.save(_custom_scale(), date(2024, 12, 31))
    b = store.save(_custom_scale(), date(2023, 12, 31))
    assert a.version_id == "2024-12-31-001"
    assert b.version_id == "2023-12-31-001"


def test_list_sorted_by_study_date_then_id(tmp_path: Path) -> None:
    """``list_versions`` returns a deterministic study-date/id ordering."""
    store = AssumptionVersionStore(tmp_path)
    store.save(_custom_scale(), date(2024, 12, 31))
    store.save(_custom_scale(), date(2023, 6, 30))
    store.save(_custom_scale(), date(2024, 12, 31))

    ids = [v.version_id for v in store.list_versions()]
    assert ids == ["2023-06-30-001", "2024-12-31-001", "2024-12-31-002"]


def test_list_filters_by_kind(tmp_path: Path) -> None:
    """A kind filter scopes the listing to that assumption family."""
    store = AssumptionVersionStore(tmp_path)
    store.save(_custom_scale(), date(2024, 12, 31))
    store.save(_custom_scale(), date(2024, 12, 31), kind="lapse_improvement")

    assert len(store.list_versions()) == 2
    assert len(store.list_versions(kind=DEFAULT_ASSUMPTION_KIND)) == 1
    assert len(store.list_versions(kind="lapse_improvement")) == 1


def test_list_empty_store(tmp_path: Path) -> None:
    """An absent store lists as empty (not an error)."""
    store = AssumptionVersionStore(tmp_path / "missing")
    assert store.list_versions() == []


def test_load_missing_version_raises(tmp_path: Path) -> None:
    """Loading an unknown id raises a clear validation error."""
    store = AssumptionVersionStore(tmp_path)
    with pytest.raises(PolarisValidationError):
        store.load("2099-01-01-001")


def test_determinism_same_saves_same_ids(tmp_path: Path) -> None:
    """The same save sequence against a fresh root yields identical ids + bytes."""
    ids_a, bytes_a = _run_saves(tmp_path / "a")
    ids_b, bytes_b = _run_saves(tmp_path / "b")
    assert ids_a == ids_b
    assert bytes_a == bytes_b


def _run_saves(root: Path) -> tuple[list[str], list[str]]:
    store = AssumptionVersionStore(root)
    ids = [
        store.save(_custom_scale(mi=0.01), date(2024, 12, 31)).version_id,
        store.save(_custom_scale(mi=0.02), date(2024, 12, 31)).version_id,
    ]
    contents = [
        (root / DEFAULT_ASSUMPTION_KIND / f"{vid}.json").read_text(encoding="utf-8") for vid in ids
    ]
    return ids, contents
