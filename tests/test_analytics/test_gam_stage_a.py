"""Tests for :mod:`polaris_re.analytics.gam_stage_a` (mgcv-parity engine, slice 1).

Anchor 1: prove the Stage-A harness on the existing, already-verified basis before
trusting it on a new one. ``extract_raw_terms``/``compare_term_extract`` are exercised
two ways here:

* pure Python, against :func:`~polaris_re.analytics.experience_mgcv_conformance.build_design`
  — always runs, no R needed;
* end to end against ``scripts/gam_term_extract.R``, gated on
  :func:`~polaris_re.analytics.experience_mgcv_conformance.rscript_mgcv_available` —
  the harness proof itself, run wherever R happens to be installed (ADR-151's own gate).
"""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import (
    DESIGNS,
    build_design,
    rscript_mgcv_available,
    synthetic_cells,
)
from polaris_re.analytics.gam_stage_a import (
    TermExtract,
    compare_term_extract,
    extract_raw_terms,
    raw_term_specs,
)
from polaris_re.analytics.gam_term_spec import TermSpec
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]

_D1 = next(d for d in DESIGNS if d.design_id == "d1")  # no factor block
_D2 = next(d for d in DESIGNS if d.design_id == "d2")  # carries a factor block


def _export_d1():
    return build_design(_D1, synthetic_cells(with_factor=False))


def _export_d2():
    return build_design(_D2, synthetic_cells(with_factor=True))


# --- TermExtract validation ----------------------------------------------------------


def test_a_well_formed_term_extract_constructs() -> None:
    design = np.zeros((5, 3))
    s = (np.eye(3), np.eye(3))
    extract = TermExtract(
        label="tensor", index_start=0, index_end=3, design=design, s=s, rank=(2, 1)
    )
    assert extract.label == "tensor"
    assert extract.knots is None


def test_index_end_must_exceed_index_start() -> None:
    with pytest.raises(PolarisValidationError, match="end must exceed start"):
        TermExtract(label="x", index_start=3, index_end=3, design=np.zeros((5, 0)), s=(), rank=())


def test_design_width_must_match_the_index_range() -> None:
    with pytest.raises(PolarisValidationError, match="index range spans"):
        TermExtract(label="x", index_start=0, index_end=3, design=np.zeros((5, 2)), s=(), rank=())


def test_penalty_blocks_must_be_square_at_the_term_width() -> None:
    with pytest.raises(PolarisValidationError, match=r"S\[0\]"):
        TermExtract(
            label="x",
            index_start=0,
            index_end=3,
            design=np.zeros((5, 3)),
            s=(np.eye(2),),
            rank=(1,),
        )


def test_rank_count_must_match_penalty_count() -> None:
    with pytest.raises(PolarisValidationError, match="one rank per S_j"):
        TermExtract(
            label="x",
            index_start=0,
            index_end=3,
            design=np.zeros((5, 3)),
            s=(np.eye(3),),
            rank=(1, 2),
        )


# --- raw_term_specs --------------------------------------------------------------------


def test_raw_term_specs_without_factor_is_the_tensor_alone() -> None:
    terms = raw_term_specs(with_factor=False)
    assert [t.label for t in terms] == ["tensor"]
    assert terms[0].basis == "raw"


def test_raw_term_specs_with_factor_adds_a_factor_term() -> None:
    terms = raw_term_specs(with_factor=True, factor_label="sex")
    assert [t.label for t in terms] == ["tensor", "factor:sex"]
    assert terms[1].variables == ("sex",)


# --- extract_raw_terms, against the already-verified fitter ---------------------------


def test_extract_raw_terms_on_d1_is_the_tensor_over_the_full_width() -> None:
    export = _export_d1()
    terms = extract_raw_terms(raw_term_specs(with_factor=False), export)
    assert set(terms) == {"tensor"}
    tensor = terms["tensor"]
    assert (tensor.index_start, tensor.index_end) == (0, export.n_tensor)
    assert tensor.design.shape == (export.n_cells, export.n_tensor)
    np.testing.assert_array_equal(tensor.design, export.design[:, : export.n_tensor])
    assert len(tensor.s) == 2
    np.testing.assert_array_equal(tensor.s[0], export.s_age[: export.n_tensor, : export.n_tensor])
    np.testing.assert_array_equal(tensor.s[1], export.s_year[: export.n_tensor, : export.n_tensor])
    assert all(r > 0 for r in tensor.rank)


def test_extract_raw_terms_on_d2_splits_off_the_factor_block() -> None:
    export = _export_d2()
    assert export.n_coef > export.n_tensor  # d2 carries a factor block
    terms = extract_raw_terms(raw_term_specs(with_factor=True, factor_label="sex"), export)
    assert set(terms) == {"tensor", "factor:sex"}
    factor = terms["factor:sex"]
    assert (factor.index_start, factor.index_end) == (export.n_tensor, export.n_coef)
    assert factor.s == ()
    assert factor.rank == ()
    np.testing.assert_array_equal(factor.design, export.design[:, export.n_tensor :])


def test_extract_raw_terms_refuses_a_non_raw_term() -> None:
    export = _export_d1()
    cr_term = TermSpec(label="s(x)", variables=("x",), basis="cr", k=(8,))
    with pytest.raises(PolarisValidationError, match="basis='raw'"):
        extract_raw_terms((cr_term,), export)


def test_extract_raw_terms_refuses_an_unrecognised_label() -> None:
    export = _export_d1()
    mystery = TermSpec(label="mystery", variables=("x",), basis="raw")
    with pytest.raises(PolarisValidationError, match="'tensor' or 'factor:"):
        extract_raw_terms((mystery,), export)


# --- compare_term_extract, self-consistency (no R) -------------------------------------


def _as_r_term(extract: TermExtract) -> dict:
    """A Python TermExtract, round-tripped into the shape the R JSON uses."""
    return {
        "index_start": extract.index_start,
        "index_end": extract.index_end,
        "X": extract.design.tolist(),
        "S": [block.tolist() for block in extract.s],
        "rank": list(extract.rank),
    }


def test_compare_term_extract_agrees_with_itself() -> None:
    export = _export_d1()
    tensor = extract_raw_terms(raw_term_specs(with_factor=False), export)["tensor"]
    comparison = compare_term_extract(tensor, _as_r_term(tensor))
    assert comparison.agrees
    assert comparison.index_range_agrees
    assert comparison.max_abs_design_diff == 0.0
    assert comparison.max_abs_s_diff == (0.0, 0.0)
    assert comparison.rank_diff == (0, 0)


def test_compare_term_extract_catches_a_moved_index_range() -> None:
    export = _export_d1()
    tensor = extract_raw_terms(raw_term_specs(with_factor=False), export)["tensor"]
    r_term = _as_r_term(tensor)
    r_term["index_start"] = 1
    comparison = compare_term_extract(tensor, r_term)
    assert not comparison.index_range_agrees
    assert not comparison.agrees


def test_compare_term_extract_catches_a_perturbed_design() -> None:
    export = _export_d1()
    tensor = extract_raw_terms(raw_term_specs(with_factor=False), export)["tensor"]
    r_term = _as_r_term(tensor)
    r_term["X"][0][0] += 1.0
    comparison = compare_term_extract(tensor, r_term)
    assert comparison.max_abs_design_diff == pytest.approx(1.0)
    assert not comparison.agrees


def test_compare_term_extract_catches_a_perturbed_penalty() -> None:
    export = _export_d1()
    tensor = extract_raw_terms(raw_term_specs(with_factor=False), export)["tensor"]
    r_term = _as_r_term(tensor)
    r_term["S"][1][0][0] += 1.0
    comparison = compare_term_extract(tensor, r_term)
    assert comparison.max_abs_s_diff[1] == pytest.approx(1.0)
    assert comparison.max_abs_s_diff[0] == 0.0
    assert not comparison.agrees


def test_compare_term_extract_catches_a_rank_disagreement() -> None:
    export = _export_d1()
    tensor = extract_raw_terms(raw_term_specs(with_factor=False), export)["tensor"]
    r_term = _as_r_term(tensor)
    r_term["rank"][0] -= 1
    comparison = compare_term_extract(tensor, r_term)
    assert comparison.rank_diff == (-1, 0)
    assert not comparison.agrees


def test_compare_term_extract_refuses_a_shape_mismatch() -> None:
    export = _export_d1()
    tensor = extract_raw_terms(raw_term_specs(with_factor=False), export)["tensor"]
    r_term = _as_r_term(tensor)
    r_term["X"] = [row[:-1] for row in r_term["X"]]
    with pytest.raises(PolarisComputationError, match="not comparable element-wise"):
        compare_term_extract(tensor, r_term)


def test_compare_term_extract_refuses_a_penalty_count_mismatch() -> None:
    export = _export_d1()
    tensor = extract_raw_terms(raw_term_specs(with_factor=False), export)["tensor"]
    r_term = _as_r_term(tensor)
    r_term["S"] = r_term["S"][:1]
    r_term["rank"] = r_term["rank"][:1]
    with pytest.raises(PolarisComputationError, match="disagree on how many penalties"):
        compare_term_extract(tensor, r_term)


# --- End to end: the R script itself, proving the harness (Anchor 1) ------------------


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_r_extractor_agrees_with_the_python_side_on_every_design(
    tmp_path,
) -> None:  # pragma: no cover
    """The harness proof itself: run ``gam_term_extract.R`` and compare term by term.

    Skipped wherever R is absent, exactly as
    ``test_the_r_script_runs_end_to_end_and_agrees`` is — this is the same class of
    test, one level down (per term rather than per cell). A disagreement here is a
    result about the harness, not the (not yet written) new bases: this basis is
    already verified to 5e-13 through the fitter (ADR-189 amendment 1), so nothing
    about the underlying arithmetic is in question, only whether this extraction
    machinery reads it correctly.
    """
    out_path = tmp_path / "gam_term_extract.json"
    done = subprocess.run(
        [
            "Rscript",
            str(REPO_ROOT / "scripts" / "gam_term_extract.R"),
            str(REPO_ROOT / "data" / "mgcv_exchange" / "synthetic"),
            str(out_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    r_payload = json.loads(out_path.read_text())

    cases = (
        ("d1", raw_term_specs(with_factor=False), _export_d1()),
        ("d2", raw_term_specs(with_factor=True, factor_label="sex"), _export_d2()),
    )
    failures: list[str] = []
    for design_id, terms, export in cases:
        python_terms = extract_raw_terms(terms, export)
        r_terms = r_payload["designs"][design_id]["terms"]
        assert set(python_terms) == set(r_terms), (
            f"design {design_id}: Python built {set(python_terms)}, R emitted {set(r_terms)}"
        )
        for label, python_term in python_terms.items():
            comparison = compare_term_extract(python_term, r_terms[label])
            if not comparison.agrees:
                failures.append(f"{design_id}/{label}: {comparison}")

    assert not failures, "Stage-A term extraction disagreed:\n" + "\n".join(failures)
