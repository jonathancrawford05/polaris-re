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
    CR_BASIS_CLAIM,
    RAW_PATH_CLAIM,
    SMOOTH_PATH_CLAIM,
    TermExtract,
    build_python_cr_term,
    compare_term_extract,
    extract_raw_terms,
    extract_smooth_terms,
    raw_term_specs,
)
from polaris_re.analytics.gam_term_spec import TermSpec
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.verification import (
    ComparisonProvenance,
    evidence_headline,
    require_parity_evidence,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

_D1 = next(d for d in DESIGNS if d.design_id == "d1")  # no factor block
_D2 = next(d for d in DESIGNS if d.design_id == "d2")  # carries a factor block
_D3 = next(d for d in DESIGNS if d.design_id == "d3")  # no factor block, a third (k_age, k_year)


def _export_d1():
    return build_design(_D1, synthetic_cells(with_factor=False))


def _export_d2():
    return build_design(_D2, synthetic_cells(with_factor=True))


def _export_d3():
    return build_design(_D3, synthetic_cells(with_factor=False))


# --- TermExtract validation ----------------------------------------------------------


def test_a_well_formed_term_extract_constructs() -> None:
    design = np.zeros((5, 3), dtype=np.float64)
    s = (np.eye(3, dtype=np.float64), np.eye(3, dtype=np.float64))
    extract = TermExtract(
        label="tensor",
        index_start=0,
        index_end=3,
        design=design,
        s=s,
        rank=(2, 1),
        evidence=RAW_PATH_CLAIM,
    )
    assert extract.label == "tensor"
    assert extract.knots is None


def test_index_end_must_exceed_index_start() -> None:
    with pytest.raises(PolarisValidationError, match="end must exceed start"):
        TermExtract(
            label="x",
            index_start=3,
            index_end=3,
            design=np.zeros((5, 0), dtype=np.float64),
            s=(),
            rank=(),
            evidence=RAW_PATH_CLAIM,
        )


def test_design_width_must_match_the_index_range() -> None:
    with pytest.raises(PolarisValidationError, match="index range spans"):
        TermExtract(
            label="x",
            index_start=0,
            index_end=3,
            design=np.zeros((5, 2), dtype=np.float64),
            s=(),
            rank=(),
            evidence=RAW_PATH_CLAIM,
        )


def test_penalty_blocks_must_be_square_at_the_term_width() -> None:
    with pytest.raises(PolarisValidationError, match=r"S\[0\]"):
        TermExtract(
            label="x",
            index_start=0,
            index_end=3,
            design=np.zeros((5, 3), dtype=np.float64),
            s=(np.eye(2, dtype=np.float64),),
            rank=(1,),
            evidence=RAW_PATH_CLAIM,
        )


def test_rank_count_must_match_penalty_count() -> None:
    with pytest.raises(PolarisValidationError, match="one rank per S_j"):
        TermExtract(
            label="x",
            index_start=0,
            index_end=3,
            design=np.zeros((5, 3), dtype=np.float64),
            s=(np.eye(3, dtype=np.float64),),
            rank=(1, 2),
            evidence=RAW_PATH_CLAIM,
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


# --- extract_smooth_terms, packaging the R-side smoothCon() extraction (slice 1b) -----


def _fake_smooth_r_term(width: int = 4, n_rows: int = 6) -> dict:
    """A well-formed, arbitrary ``RTermPayload``-shaped dict for testing
    :func:`extract_smooth_terms`'s packaging (index range, design, S, rank, knots) —
    not any particular basis's numbers, which the R-gated end-to-end test below
    covers against the real ``smoothCon()`` extraction."""
    return {
        "index_start": 0,
        "index_end": width,
        "X": [[float(r * width + c) for c in range(width)] for r in range(n_rows)],
        "S": [[[1.0 if i == j else 0.0 for j in range(width)] for i in range(width)]],
        "rank": [width - 1],
        "knots": [float(k) for k in range(width + 2)],
    }


def test_extract_smooth_terms_builds_a_term_extract_from_the_r_payload() -> None:
    r_term = _fake_smooth_r_term(width=4, n_rows=6)
    cr_term = TermSpec(label="s(x)", variables=("x",), basis="cr", k=(4,))
    terms = extract_smooth_terms((cr_term,), {"s(x)": r_term})
    assert set(terms) == {"s(x)"}
    extract = terms["s(x)"]
    assert (extract.index_start, extract.index_end) == (0, 4)
    assert extract.design.shape == (6, 4)
    assert len(extract.s) == 1
    assert extract.s[0].shape == (4, 4)
    assert extract.rank == (3,)
    assert extract.knots == tuple(float(k) for k in range(6))


def test_extract_smooth_terms_refuses_a_raw_term() -> None:
    raw_term = TermSpec(label="tensor", variables=("attained_age", "calendar_year"), basis="raw")
    with pytest.raises(PolarisValidationError, match="mgcv-native bases"):
        extract_smooth_terms((raw_term,), {})


def test_extract_smooth_terms_refuses_a_label_with_no_r_payload_entry() -> None:
    cr_term = TermSpec(label="s(missing)", variables=("x",), basis="cr", k=(4,))
    with pytest.raises(PolarisValidationError, match="no matching entry"):
        extract_smooth_terms((cr_term,), {"s(x)": _fake_smooth_r_term()})


# --- compare_term_extract, self-consistency (no R) -------------------------------------


def _as_r_term(extract: TermExtract) -> dict:
    """A Python TermExtract, round-tripped into the shape the R JSON uses."""
    return {
        "index_start": extract.index_start,
        "index_end": extract.index_end,
        "X": extract.design.tolist(),
        "S": [block.tolist() for block in extract.s],
        "rank": list(extract.rank),
        "knots": list(extract.knots) if extract.knots is not None else None,
    }


def test_compare_term_extract_agrees_with_itself() -> None:
    export = _export_d1()
    tensor = extract_raw_terms(raw_term_specs(with_factor=False), export)["tensor"]
    comparison = compare_term_extract(tensor, _as_r_term(tensor))
    assert comparison.agrees
    assert comparison.index_range_agrees
    # Exact 0.0, not pytest.approx: `_as_r_term` round-trips through tolist()/asarray
    # losslessly, so the diff against itself is exactly zero by construction, not
    # approximately zero by floating-point luck. Weakening this to a tolerance would
    # weaken what the test actually checks (PR #197 review [P2]).
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


# --- compare_term_extract, knots (slice 1b) ---------------------------------------------


def test_compare_term_extract_knots_agree_when_both_absent() -> None:
    export = _export_d1()
    tensor = extract_raw_terms(raw_term_specs(with_factor=False), export)["tensor"]
    comparison = compare_term_extract(tensor, _as_r_term(tensor))
    assert comparison.knots_agree
    assert comparison.max_abs_knots_diff is None
    assert comparison.agrees


def test_compare_term_extract_knots_agree_when_both_present_and_equal() -> None:
    r_term = _fake_smooth_r_term(width=4, n_rows=6)
    cr_term = TermSpec(label="s(x)", variables=("x",), basis="cr", k=(4,))
    extract = extract_smooth_terms((cr_term,), {"s(x)": r_term})["s(x)"]
    comparison = compare_term_extract(extract, r_term)
    assert comparison.knots_agree
    assert comparison.max_abs_knots_diff == 0.0
    assert comparison.agrees


def test_compare_term_extract_catches_a_perturbed_knot() -> None:
    r_term = _fake_smooth_r_term(width=4, n_rows=6)
    cr_term = TermSpec(label="s(x)", variables=("x",), basis="cr", k=(4,))
    extract = extract_smooth_terms((cr_term,), {"s(x)": r_term})["s(x)"]
    perturbed = dict(r_term)
    perturbed["knots"] = list(r_term["knots"])
    perturbed["knots"][0] += 1.0
    comparison = compare_term_extract(extract, perturbed)
    assert not comparison.knots_agree
    assert comparison.max_abs_knots_diff == pytest.approx(1.0)
    assert not comparison.agrees


def test_compare_term_extract_catches_a_knots_presence_mismatch() -> None:
    export = _export_d1()
    tensor = extract_raw_terms(raw_term_specs(with_factor=False), export)["tensor"]
    r_term = _as_r_term(tensor)
    r_term["knots"] = [1.0, 2.0, 3.0]  # R now claims knots; Python's TermExtract still None
    comparison = compare_term_extract(tensor, r_term)
    assert not comparison.knots_agree
    assert comparison.max_abs_knots_diff is None
    assert not comparison.agrees


def test_compare_term_extract_refuses_a_knots_shape_mismatch() -> None:
    r_term = _fake_smooth_r_term(width=4, n_rows=6)
    cr_term = TermSpec(label="s(x)", variables=("x",), basis="cr", k=(4,))
    extract = extract_smooth_terms((cr_term,), {"s(x)": r_term})["s(x)"]
    shortened = dict(r_term)
    shortened["knots"] = r_term["knots"][:-1]
    with pytest.raises(PolarisComputationError, match="not comparable element-wise"):
        compare_term_extract(extract, shortened)


# --- build_python_cr_term, the independent Python producer (slice 2) -------------------


def test_build_python_cr_term_builds_a_term_extract_with_supplied_knots() -> None:
    rng = np.random.default_rng(1)
    x = np.sort(rng.uniform(0.0, 10.0, 100))
    term = TermSpec(
        label="s(x)",
        variables=("x",),
        basis="cr",
        k=(8,),
        knots=(("x", (0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0)),),
    )
    extract = build_python_cr_term(x, term)
    assert extract.label == "s(x)"
    assert (extract.index_start, extract.index_end) == (0, 7)
    assert extract.design.shape == (100, 7)
    assert len(extract.s) == 1
    assert extract.s[0].shape == (7, 7)
    assert extract.knots == (0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0)
    assert extract.evidence is CR_BASIS_CLAIM


def test_build_python_cr_term_derives_default_knots_when_none_supplied() -> None:
    rng = np.random.default_rng(2)
    x = np.sort(rng.uniform(0.0, 10.0, 200))
    term = TermSpec(label="s(x)", variables=("x",), basis="cr", k=(8,))
    extract = build_python_cr_term(x, term)
    assert extract.knots is not None
    assert len(extract.knots) == 8
    assert extract.knots[0] == pytest.approx(float(np.min(x)))
    assert extract.knots[-1] == pytest.approx(float(np.max(x)))


def test_build_python_cr_term_refuses_a_non_cr_basis() -> None:
    x = np.linspace(0.0, 10.0, 50)
    raw_term = TermSpec(label="tensor", variables=("attained_age", "calendar_year"), basis="raw")
    with pytest.raises(PolarisValidationError, match="basis='cr'"):
        build_python_cr_term(x, raw_term)


def test_build_python_cr_term_refuses_more_than_one_variable() -> None:
    # basis='cr' does not itself forbid a second variable at TermSpec construction
    # (that restriction is ti/sz-specific) — build_python_cr_term is what refuses it.
    x = np.linspace(0.0, 10.0, 50)
    two_var_term = TermSpec(label="s(a,b)", variables=("a", "b"), basis="cr", k=(8, 6))
    with pytest.raises(PolarisValidationError, match="exactly one variable"):
        build_python_cr_term(x, two_var_term)


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
        # The R extractor emits d3 too (a third (k_age, k_year) pair) but the manifest
        # names no cell reaching it through this script's other test — d1/d2 alone left
        # its output produced and silently discarded (PR #197 review [P2]).
        ("d3", raw_term_specs(with_factor=False), _export_d3()),
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


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_r_extractor_agrees_with_the_python_side_on_every_smooth_design(
    tmp_path,
) -> None:  # pragma: no cover
    """Slice 1b's harness proof: ``gam_term_extract.R``'s ``smoothCon()`` branch,
    packaged through :func:`extract_smooth_terms`, round-trips through
    :func:`compare_term_extract` without disagreement.

    What this test verifies is the Python-side *packaging*, not the extraction's
    correctness — the R script emits per-term data straight from
    ``smoothCon(absorb.cons=TRUE)`` and :func:`extract_smooth_terms` reads it
    directly (there is no independent Python ``cr`` basis yet, slice 2), so this
    cannot disagree unless the JSON round trip or the packaging itself is broken. The
    extraction's correctness is what the R script's OWN internal guard re-verifies on
    every run (against ``predict(type="lpmatrix")`` / ``m$smooth[[j]]``, ADR-191) —
    a nonzero guard trips ``done.returncode`` below before this test's own assertions
    run at all.
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
    smooth_designs = r_payload["smooth_designs"]
    assert set(smooth_designs) == set(_SMOOTH_CASES)

    terms = tuple(
        TermSpec(label=label, variables=("x",), basis="cr", k=(len(r_term["knots"]),))
        for label, r_term in smooth_designs.items()
    )
    python_terms = extract_smooth_terms(terms, smooth_designs)

    failures: list[str] = []
    for label, python_term in python_terms.items():
        comparison = compare_term_extract(python_term, smooth_designs[label])
        if not comparison.agrees:
            failures.append(f"{label}: {comparison}")

    assert not failures, "Stage-A mgcv-native term extraction disagreed:\n" + "\n".join(failures)


# The (k, knots) recipe for each of gam_term_extract.R's five `extract_smooth_one`
# cases, named explicitly here rather than inferred from the R payload —
# build_python_cr_term must use the SAME recipe R was given (Anchor 4: never derive
# knots when supplied), and reading either k or the knot values back off the R
# payload would violate ADR-193's mechanical test — a k mismatch could otherwise
# never surface as a disagreement (PR #201 review [P2]).
_SMOOTH_CASES: dict[str, tuple[int, tuple[float, ...] | None, bool]] = {
    "default-knots-k8": (8, None, False),
    "default-knots-k13": (13, None, False),
    "supplied-knots-k8": (8, (0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0), False),
    # PLAN §1's actual target formula: s(AttdAge, k=13, bs="cr") / s(PolYear, k=6,
    # bs="cr") — slice 2 acceptance criterion #1 names these knot vectors, not a
    # stand-in.
    "target-attdage-k13": (
        13,
        (1.0, 2.0, 4.0, 7.0, 14.0, 18.0, 24.0, 35.0, 50.0, 70.0, 85.0, 90.0, 95.0),
        False,
    ),
    "target-polyear-k6": (6, (1.0, 2.0, 3.0, 5.0, 10.0, 21.0), False),
    # Slice 5, the MI term's own basis: s(AttdAge, by=StudyYear_C, k=13, bs="cr") —
    # same target AttdAge knots, now with a numeric by variable (`with_by = TRUE`
    # in gam_term_extract.R's extract_smooth_one).
    "mi-term-attdage-by-k13": (
        13,
        (1.0, 2.0, 4.0, 7.0, 14.0, 18.0, 24.0, 35.0, 50.0, 70.0, 85.0, 90.0, 95.0),
        True,
    ),
}


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_python_cr_basis_agrees_with_smoothcon_on_every_smooth_design(
    tmp_path,
) -> None:  # pragma: no cover
    """Slice 2's harness proof, and the epic's first INDEPENDENT Stage-A result:
    :func:`build_python_cr_term` — a Python ``cr`` basis built from Wood's
    natural-cubic-spline definition — agrees with ``mgcv``'s own
    ``smoothCon(absorb.cons=TRUE)``, read via the R script's ``x`` export, on all
    five of ``gam_term_extract.R``'s isolated ``bs="cr"`` cases — including the
    target formula's own ``AttdAge``/``PolYear`` knot vectors, not just the
    original harness's synthetic ones.

    A disagreement here is a *result about the basis* (ADR-193's "what a good
    session looks like"), not a broken round trip — unlike the TRANSPORT test
    above, this one can genuinely fail on the numbers.
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
    smooth_designs = r_payload["smooth_designs"]
    assert set(smooth_designs) == set(_SMOOTH_CASES)

    failures: list[str] = []
    for label, r_term in smooth_designs.items():
        k, supplied, with_by = _SMOOTH_CASES[label]
        term = TermSpec(
            label=label,
            variables=("x",),
            basis="cr",
            k=(k,),
            knots=(("x", supplied),) if supplied is not None else None,
            by="z" if with_by else None,
        )
        x = np.asarray(r_term["x"], dtype=np.float64)
        by = np.asarray(r_term["by"], dtype=np.float64) if with_by else None
        python_term = build_python_cr_term(x, term, by=by)
        assert python_term.evidence is CR_BASIS_CLAIM
        # Passes the FULL quantity set, not just parity_quantities — a claim that
        # ever regressed to carrying a non-INDEPENDENT quantity must fail this gate
        # (PR #201 review [P2]; `parity_quantities` pre-filters, so gating on it
        # can only catch an empty claim).
        require_parity_evidence(
            python_term.evidence.quantities, claim=f"{label}: Stage-A cr basis parity"
        )
        comparison = compare_term_extract(python_term, r_term)
        if not comparison.agrees:
            failures.append(
                f"{label}: max_X_diff={comparison.max_abs_design_diff:.3e} "
                f"max_S_diff={comparison.max_abs_s_diff} rank_diff={comparison.rank_diff} "
                f"knots_agree={comparison.knots_agree}"
            )

    assert not failures, "Stage-A cr basis parity disagreed:\n" + "\n".join(failures)


# --- Provenance: what these comparisons are evidence OF (ADR-193) ----------------------


def test_the_raw_path_declares_its_design_and_penalties_as_echoed() -> None:
    """The raw path hands mgcv the design and penalties it then reads back, so a
    zero diff on those columns proves no tampering — not that two sides agree."""
    export = _export_d1()
    tensor = extract_raw_terms(raw_term_specs(with_factor=False), export)["tensor"]
    by_name = {q.quantity: q for q in tensor.evidence.quantities}
    assert by_name["design_X"].provenance is ComparisonProvenance.ECHO
    assert by_name["penalty_S"].provenance is ComparisonProvenance.ECHO
    assert not tensor.evidence.is_parity_claim


def test_the_raw_paths_rank_is_the_one_independently_produced_column() -> None:
    export = _export_d1()
    tensor = extract_raw_terms(raw_term_specs(with_factor=False), export)["tensor"]
    assert [q.quantity for q in tensor.evidence.parity_quantities] == ["rank"]
    require_parity_evidence(tensor.evidence.parity_quantities, claim="mgcv's own rank agrees")


def test_the_mgcv_native_path_declares_every_quantity_as_transport() -> None:
    """Slice 1b parses the R payload and compares it to that same payload: no
    column there can disagree on values, and the claim now says so in the type."""
    cr_term = TermSpec(label="s(x)", variables=("x",), basis="cr", k=(4,))
    extract = extract_smooth_terms((cr_term,), {"s(x)": _fake_smooth_r_term()})["s(x)"]
    assert extract.evidence is SMOOTH_PATH_CLAIM
    assert extract.evidence.parity_quantities == ()
    assert all(q.provenance is ComparisonProvenance.TRANSPORT for q in extract.evidence.quantities)


def test_a_parity_claim_over_the_mgcv_native_path_is_refused() -> None:
    """The gate that would have caught slice 1b being reported as Stage-A parity."""
    cr_term = TermSpec(label="s(x)", variables=("x",), basis="cr", k=(4,))
    extract = extract_smooth_terms((cr_term,), {"s(x)": _fake_smooth_r_term()})["s(x)"]
    with pytest.raises(PolarisValidationError, match="not independently"):
        require_parity_evidence(extract.evidence.quantities, claim="Stage A exact for bs='cr'")


def test_a_comparison_carries_its_producers_provenance_through() -> None:
    export = _export_d1()
    tensor = extract_raw_terms(raw_term_specs(with_factor=False), export)["tensor"]
    comparison = compare_term_extract(tensor, _as_r_term(tensor))
    assert comparison.agrees
    assert comparison.evidence is RAW_PATH_CLAIM
    # The verdict a report prints above the zeros, derived from the declaration.
    assert "NOT basis parity" in evidence_headline(comparison.evidence)


def test_the_python_cr_basis_declares_every_quantity_independent() -> None:
    """Slice 2 (ADR-193): the first Stage-A claim entitled to say "parity"."""
    rng = np.random.default_rng(3)
    x = np.sort(rng.uniform(0.0, 10.0, 50))
    term = TermSpec(label="s(x)", variables=("x",), basis="cr", k=(8,))
    extract = build_python_cr_term(x, term)
    assert extract.evidence is CR_BASIS_CLAIM
    assert extract.evidence.is_parity_claim
    assert all(
        q.provenance is ComparisonProvenance.INDEPENDENT for q in extract.evidence.quantities
    )
    assert "Parity comparison" in evidence_headline(extract.evidence)
    require_parity_evidence(extract.evidence.parity_quantities, claim="cr basis parity")


def test_the_python_cr_basis_claim_excludes_knots() -> None:
    """PR #201 review [P1]: `knots` is ECHO in 3 of slice 2's 5 cases (both sides
    relay the same hand-declared literal when knots are supplied), so it cannot
    honestly carry a single per-quantity INDEPENDENT tag and is excluded from
    CR_BASIS_CLAIM rather than mislabelled — knot agreement is still checked
    (compare_term_extract's knots_agree), just outside this claim."""
    assert {q.quantity for q in CR_BASIS_CLAIM.quantities} == {"design_X", "penalty_S", "rank"}
    assert "knots" not in {q.quantity for q in CR_BASIS_CLAIM.quantities}
