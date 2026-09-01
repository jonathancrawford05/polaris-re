"""``docs/PLAN_mgcv_parity_engine.md`` slice 7 — ``select = TRUE``'s double
penalty, Stage A.

R-free tests assert :func:`~polaris_re.analytics.gam_select_penalty.null_space_penalty`'s
own algebraic invariants (it is a genuine orthogonal projector onto a known
null space, for both a single block and several summed together) — checkable
without ``mgcv``, the same "an oracle outage delays the measurement without
idling the session" framing ``test_gam_model.py`` uses. The real parity
check — Python's independently-computed ``S_null`` against ``mgcv``'s own
``gam(..., select=TRUE, fit=FALSE)$smooth[[i]]$S`` — is the R-gated test at
the bottom, covering every term archetype the target formula uses (``cr``,
numeric-``by`` ``cr``, ``ti``, ``sz``), at the target's own knot vectors.
"""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_select_penalty import (
    SELECT_PENALTY_CLAIM,
    compare_null_space_penalty,
    null_space_penalty,
)
from polaris_re.analytics.gam_stage_a import (
    build_python_cr_term,
    build_python_sz_term,
    build_python_ti_term,
)
from polaris_re.analytics.gam_term_spec import TermSpec
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_AGE_KNOTS = (1.0, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)
_YEAR_KNOTS = (1.0, 2, 3, 5, 10, 21)


def _random_orthonormal(p: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    q, _ = np.linalg.qr(rng.normal(size=(p, p)))
    return q


def test_null_space_penalty_is_a_projector_onto_the_known_null_space() -> None:
    """A single block with a KNOWN rank deficiency: eigenvalues
    ``[5, 3, 1, 0, 0]`` in a random orthonormal basis, so the null space is
    exactly the span of the last two eigenvectors."""
    p = 5
    v = _random_orthonormal(p, seed=1)
    eigenvalues = np.array([5.0, 3.0, 1.0, 0.0, 0.0])
    s = v @ np.diag(eigenvalues) @ v.T
    s = (s + s.T) / 2.0

    result = null_space_penalty((s,))
    assert result is not None
    s_null, null_dim = result
    assert null_dim == 2
    assert s_null.shape == (p, p)

    # Symmetric.
    np.testing.assert_allclose(s_null, s_null.T, atol=1e-12)
    # Idempotent -- a genuine orthogonal projector (U0 orthonormal).
    np.testing.assert_allclose(s_null @ s_null, s_null, atol=1e-10)
    # Rank equals the null dimension.
    assert np.linalg.matrix_rank(s_null) == 2
    # Projects the known null-space eigenvectors onto themselves...
    null_vectors = v[:, 3:]
    np.testing.assert_allclose(s_null @ null_vectors, null_vectors, atol=1e-10)
    # ...and every range-space eigenvector to zero.
    range_vectors = v[:, :3]
    np.testing.assert_allclose(s_null @ range_vectors, 0.0, atol=1e-10)
    # S_null and the original S share no non-null direction (orthogonal
    # projectors onto complementary spaces).
    np.testing.assert_allclose(s_null @ s, 0.0, atol=1e-8)


def test_null_space_penalty_combines_several_blocks_before_the_null_space() -> None:
    """Two blocks whose INDIVIDUAL null spaces differ, but whose SUM has a
    known, smaller null space — the same "combine first" rule measured
    against ``mgcv`` for ``ti``/``sz`` (module docstring): the null space is
    of the blocks' unscaled SUM, not of any one block alone."""
    p = 4
    v = _random_orthonormal(p, seed=2)
    # Block 1 penalizes directions 0,1; block 2 penalizes 0,2. Their sum
    # penalizes 0,1,2, leaving only direction 3 unpenalized.
    s1 = v @ np.diag([1.0, 1.0, 0.0, 0.0]) @ v.T
    s2 = v @ np.diag([1.0, 0.0, 1.0, 0.0]) @ v.T
    s1, s2 = (s1 + s1.T) / 2.0, (s2 + s2.T) / 2.0

    result = null_space_penalty((s1, s2))
    assert result is not None
    s_null, null_dim = result
    assert null_dim == 1
    null_vector = v[:, 3:4]
    np.testing.assert_allclose(s_null @ null_vector, null_vector, atol=1e-10)
    range_vectors = v[:, :3]
    np.testing.assert_allclose(s_null @ range_vectors, 0.0, atol=1e-10)


def test_null_space_penalty_returns_none_for_a_full_rank_block() -> None:
    """A full-rank penalty has nothing left to penalize -- `select = TRUE`
    would add no extra block for a term shaped like this."""
    p = 4
    v = _random_orthonormal(p, seed=3)
    s = v @ np.diag([5.0, 3.0, 1.0, 0.5]) @ v.T
    assert null_space_penalty(((s + s.T) / 2.0,)) is None


def test_null_space_penalty_rejects_empty_blocks() -> None:
    with pytest.raises(PolarisValidationError, match="at least one"):
        null_space_penalty(())


def test_null_space_penalty_rejects_mismatched_shapes() -> None:
    with pytest.raises(PolarisValidationError, match="mismatched shapes"):
        null_space_penalty((np.eye(3), np.eye(4)))


def test_null_space_penalty_rejects_non_square_blocks() -> None:
    with pytest.raises(PolarisValidationError, match="not square"):
        null_space_penalty((np.zeros((3, 4)),))


def test_select_penalty_claim_is_independent() -> None:
    """ADR-193's gate: a harness result must not be able to satisfy this."""
    require_parity_evidence(SELECT_PENALTY_CLAIM.quantities, claim=SELECT_PENALTY_CLAIM.claim)
    assert SELECT_PENALTY_CLAIM.is_parity_claim


def test_compare_null_space_penalty_rejects_a_block_count_mismatch() -> None:
    p = 4
    v = _random_orthonormal(p, seed=4)
    s = (v @ np.diag([5.0, 3.0, 0.0, 0.0]) @ v.T + v @ np.diag([5.0, 3.0, 0.0, 0.0]) @ v.T.T) / 2.0
    r_case = {"S": [s.tolist(), s.tolist(), np.zeros((p, p)).tolist()], "rank": [2, 2, 0]}
    with pytest.raises(Exception, match="expected R to carry exactly one more"):
        compare_null_space_penalty("synthetic", (s,), r_case)


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_r_probe_runs_end_to_end_and_agrees(tmp_path) -> None:  # pragma: no cover
    """The real conformance run: every target-formula term archetype's
    null-space penalty, independently computed in Python from that term's
    own already-verified basis producer, against ``mgcv``'s own
    ``select=TRUE`` setup path — see the module docstrings for the claim
    and how the rule was derived. A disagreement here is a real result
    (PLAN Anchor 9), not a test bug to paper over.
    """
    out_path = tmp_path / "gam_select_penalty_probe.json"
    done = subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_select_penalty_probe.R"), str(out_path)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr

    payload = json.loads(out_path.read_text())
    cases = payload["cases"]

    def arr(case: str, key: str) -> np.ndarray:
        return np.asarray(cases[case][key], dtype=np.float64)

    results = {}

    age_x = arr("cr-ref-attdage-k13", "x")
    term = TermSpec(
        label="s(AttdAge)",
        variables=("AttdAge",),
        basis="cr",
        k=(13,),
        knots=(("AttdAge", _AGE_KNOTS),),
    )
    extract = build_python_cr_term(age_x, term)
    results["cr-ref-attdage-k13"] = compare_null_space_penalty(
        "cr-ref-attdage-k13", extract.s, cases["cr-ref-attdage-k13"]
    )

    year_x = arr("cr-ref-polyear-k6", "x")
    term2 = TermSpec(
        label="s(PolYear)",
        variables=("PolYear",),
        basis="cr",
        k=(6,),
        knots=(("PolYear", _YEAR_KNOTS),),
    )
    extract2 = build_python_cr_term(year_x, term2)
    results["cr-ref-polyear-k6"] = compare_null_space_penalty(
        "cr-ref-polyear-k6", extract2.s, cases["cr-ref-polyear-k6"]
    )

    by_x = arr("cr-by-mi-attdage-k13", "x")
    by_var = arr("cr-by-mi-attdage-k13", "by_var")
    term3 = TermSpec(
        label="s(AttdAge,by=StudyYear_C)",
        variables=("AttdAge",),
        basis="cr",
        k=(13,),
        knots=(("AttdAge", _AGE_KNOTS),),
        by="StudyYear_C",
    )
    extract3 = build_python_cr_term(by_x, term3, by=by_var)
    results["cr-by-mi-attdage-k13"] = compare_null_space_penalty(
        "cr-by-mi-attdage-k13", extract3.s, cases["cr-by-mi-attdage-k13"]
    )

    ti_x1 = arr("ti-attdage-polyear", "x")
    ti_x2 = arr("ti-attdage-polyear", "x2")
    term4 = TermSpec(
        label="ti(AttdAge,PolYear)",
        variables=("AttdAge", "PolYear"),
        basis="ti",
        k=(13, 6),
        knots=(("AttdAge", _AGE_KNOTS), ("PolYear", _YEAR_KNOTS)),
    )
    extract4 = build_python_ti_term(ti_x1, ti_x2, term4)
    results["ti-attdage-polyear"] = compare_null_space_penalty(
        "ti-attdage-polyear", extract4.s, cases["ti-attdage-polyear"]
    )

    for case, x_var in (
        ("sz-facesize-attdage-k13", _AGE_KNOTS),
        ("sz-facesize-polyear-k6", _YEAR_KNOTS),
    ):
        x = arr(case, "x")
        group = np.asarray(cases[case]["group"], dtype=np.int64)
        n_levels = int(cases[case]["n_levels"])
        var_name = "AttdAge" if "attdage" in case else "PolYear"
        term_sz = TermSpec(
            label=f"s(FaceSize,{var_name})",
            variables=("FaceSize", var_name),
            basis="sz",
            k=(len(x_var),),
            knots=((var_name, x_var),),
            n_levels=n_levels,
        )
        extract_sz = build_python_sz_term(x, group, n_levels, term_sz)
        results[case] = compare_null_space_penalty(case, extract_sz.s, cases[case])

    assert set(results) == set(cases)
    for case, comparison in results.items():
        assert comparison.agrees, (case, comparison.max_abs_s_null_diff, comparison.null_dim)
