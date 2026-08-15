"""
Tests for the ``mgcv`` conformance suite (penalized MI surface, slice 5 — ADR-189).

**None of these tests need R.** That is deliberate and it is the slice's central design
claim rather than a convenience: the exported problem is a penalized Poisson GLM over a
*shared* design, whose log-likelihood is strictly concave, so its maximiser is unique.
:func:`penalized_score_infinity_norm` verifies that the exported coefficients sit at that
maximiser, which pins what any conformant R solver must return — without R present. The
R path itself is gated by :func:`rscript_mgcv_available` exactly as ADR-151 established,
so CI and the Docker runtime skip it rather than fail (PLAN Anchor 5 of the A4' epic:
CI never grows an R dependency).

The comparator gets both directions. A comparator that cannot fail is not a check, so
every metric is exercised against a **seeded known disagreement** at a perturbation the
tolerance must reject, alongside the known-agreement case.
"""

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_gam_penalized import (
    KS_LOG_STEP,
    REFINE_STEP,
    PenalizedTensorMIModel,
    tensor_penalties,
)
from polaris_re.analytics.experience_mgcv_conformance import (
    CONFORMANCE_CELLS,
    DESIGNS,
    LEVEL_METRICS,
    SCHEMA_VERSION,
    ConformanceCell,
    DesignSpec,
    build_exchange,
    compare_reference,
    exchange_hash,
    penalized_score_infinity_norm,
    python_reference,
    read_exchange,
    render_comparison_markdown,
    rscript_mgcv_available,
    synthetic_cells,
    write_exchange,
    write_python_reference,
)
from polaris_re.core.exceptions import PolarisValidationError

pytestmark = pytest.mark.filterwarnings(
    "ignore::statsmodels.tools.sm_exceptions.PerfectSeparationWarning"
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_EXCHANGE = REPO_ROOT / "data" / "mgcv_exchange" / "synthetic"

_SCORE_CEILING = 1.0e-6
"""Absolute ceiling on ``||Xᵀ(y - μ) - Sβ||∞`` across every committed cell.

**Chosen, not fitted.** Deaths in these cells are O(1e2-1e3), so the score's natural
scale is counts; the measured worst cell is ~2.2e-10, four orders below this bound. The
ceiling is a bound on what "at the maximiser" means for this problem rather than a
record of what the code happened to produce — a test that compares against the constant
the code hardcoded cannot fail (ADR-186's ``lambda_grid_step`` lesson), and neither can
one whose threshold was read off the output."""

# A single small design, for the tests that only need the machinery rather than the
# committed matrix. `k_year=4` is the floor for degree 3 (full marginal bases), which
# keeps the fits to a few milliseconds.
_TINY = (DesignSpec("t1", 5, 4, False), DesignSpec("t2", 5, 4, True))
_TINY_CELLS = (
    ConformanceCell("fixed", "t1", (1, 3, 4), 100.0, 10.0),
    ConformanceCell("fixed-factors", "t2", (1, 3), 100.0, 10.0),
)


@pytest.fixture(scope="module")
def tiny_bundle():
    return build_exchange("tiny", designs=_TINY, conformance_cells=_TINY_CELLS)


@pytest.fixture(scope="module")
def tiny_written(tmp_path_factory, tiny_bundle):
    """The tiny exchange plus our reference, written once for the whole module."""
    out = tmp_path_factory.mktemp("tiny-exchange")
    digest = write_exchange(tiny_bundle, out)
    results = python_reference(tiny_bundle)
    write_python_reference(results, out, exchange_digest=digest, case="tiny")
    return out, digest, results


def _mirror_as_mgcv(python_ref: dict) -> dict:
    """A synthetic ``mgcv`` reference that agrees with ours **exactly**.

    The R side's payload mirrors the Python side's field-for-field on every compared
    quantity, so copying it is the known-agreement case. Everything below perturbs this
    to build the known-disagreement cases — which is the only way a tolerance can be
    shown to bite rather than merely to exist.
    """
    mirrored = copy.deepcopy(python_ref)
    mirrored["side"] = "mgcv"
    mirrored["mgcv_version"] = "1.9-1"
    mirrored["r_version"] = "R version 4.4.1 (2024-06-14)"
    mirrored["r_session_info"] = "R version 4.4.1 (2024-06-14)\nmgcv_1.9-1"
    mirrored["scale_penalty"] = False
    return mirrored


# --------------------------------------------------------------------------- #
# The case matrix — what PLAN slice 5 asked the export to cover
# --------------------------------------------------------------------------- #


def test_the_case_matrix_covers_every_level_and_regime_the_plan_names() -> None:
    """PLAN slice 5's build requirement 2: *export a matrix, not a case*.

    "A single case can agree by accident" is the reason, and the specific accident named
    in the PR #190 review is the λ-relative-to-φ convention, which only an asymmetric λ
    pair exposes. This asserts the coverage rather than trusting the literal above it:
    all five levels, three fixed-λ pairs including both saturated corners, two ``k``
    pairs, and a factor block present and absent.
    """
    levels = {level for cell in CONFORMANCE_CELLS for level in cell.levels}
    assert levels == {1, 2, 3, 4, 5}

    fixed = [c for c in CONFORMANCE_CELLS if not c.free_sp]
    assert len(fixed) >= 3
    pairs = {(c.lambda_age, c.lambda_year) for c in fixed}
    assert len(pairs) >= 3, "three distinct fixed-lambda pairs, per the plan"
    assert any(c.lambda_age > 1e5 for c in fixed), "an age-saturated corner"
    assert any(c.lambda_year is not None and c.lambda_year > 1e5 for c in fixed), "a year corner"
    # The convention cell: lambdas three decades apart in opposite directions.
    assert any(abs(np.log10(c.lambda_age) - np.log10(c.lambda_year)) >= 3.0 for c in fixed), (
        "an asymmetric lambda pair, or a scale-convention error stays hidden"
    )

    used = {c.design_id for c in CONFORMANCE_CELLS}
    specs = [d for d in DESIGNS if d.design_id in used]
    assert len({(d.k_age, d.k_year) for d in specs}) >= 2, "two (k_age, k_year) pairs"
    assert {d.with_factor for d in specs} == {True, False}, "with and without a factor block"
    assert any(c.gamma != 1.0 for c in CONFORMANCE_CELLS), "a gamma cell for level 5"
    assert 8 <= len(CONFORMANCE_CELLS) <= 12, "the plan's ~8-12 cells"


def test_the_second_k_pair_moves_both_margins() -> None:
    """A second pair that widened only one margin would leave a Kronecker bug alive.

    The tensor design is a **row-wise Kronecker product**, age-major. A column-ordering
    or transposition error swaps the roles of the two margins, and a second design that
    changed only ``k_age`` could keep the same product shape and hide it.
    """
    used = {c.design_id for c in CONFORMANCE_CELLS}
    pairs = sorted({(d.k_age, d.k_year) for d in DESIGNS if d.design_id in used})
    first, second = pairs[0], pairs[-1]
    assert first[0] != second[0] and first[1] != second[1]


def test_a_cell_naming_an_unbuilt_design_is_refused() -> None:
    """The failure R would otherwise hit halfway through a batch of ten fits."""
    with pytest.raises(PolarisValidationError, match="does not build"):
        build_exchange(
            "broken",
            designs=_TINY,
            conformance_cells=(ConformanceCell("orphan", "nope", (1,), 1.0, 1.0),),
        )


# --------------------------------------------------------------------------- #
# The exchange: round-trip, and the hash that certifies it
# --------------------------------------------------------------------------- #


def test_the_exchange_round_trips_every_number_bit_exactly(tiny_written, tiny_bundle) -> None:
    """``%.17g`` round-trips an IEEE-754 double, so R fits the design Python fit.

    Asserted with :func:`np.array_equal` rather than a tolerance on purpose. Anything
    looser here would make every level-1 disagreement partly a formatting artefact, and
    level 1 is the foundation the other four localise against.
    """
    out, _, _ = tiny_written
    reread = read_exchange(out)
    assert set(reread.designs) == set(tiny_bundle.designs)
    for design_id, export in tiny_bundle.designs.items():
        back = reread.designs[design_id]
        for field in ("design", "deaths", "offset", "s_age", "s_year"):
            assert np.array_equal(getattr(export, field), getattr(back, field)), field
        assert back.n_tensor == export.n_tensor
        assert back.factors == export.factors
        assert back.spec == export.spec
    assert reread.cells == tiny_bundle.cells


def test_the_exported_penalty_is_the_penalty_the_fit_actually_uses(tiny_bundle) -> None:
    """R must penalise what we penalise, so the padded block is compared to the fitter's.

    The exchange ships the penalties **padded to the full design width** because
    ``paraPen`` wants one matrix per penalty at the term's own dimension, and the padding
    is what tells R the factor columns are unpenalised. If the padding were wrong, R
    would shrink a factor coefficient we do not, and level 1 would disagree for a reason
    that looks like arithmetic.
    """
    for design_id, export in tiny_bundle.designs.items():
        s_age, s_year = tensor_penalties(export.spec.k_age, export.spec.k_year)
        n = export.n_tensor
        np.testing.assert_allclose(export.s_age[:n, :n], s_age, rtol=0.0, atol=0.0)
        np.testing.assert_allclose(export.s_year[:n, :n], s_year, rtol=0.0, atol=0.0)
        # Everything outside the tensor block is exactly zero — the factor columns.
        assert export.s_age[n:, :].sum() == 0.0 and export.s_age[:, n:].sum() == 0.0, design_id
        assert export.s_year[n:, :].sum() == 0.0 and export.s_year[:, n:].sum() == 0.0, design_id


def test_the_exchange_hash_moves_when_any_exported_number_moves(tmp_path, tiny_bundle) -> None:
    """The guard is only a guard if it is sensitive to the thing it certifies."""
    first = tmp_path / "a"
    digest = write_exchange(tiny_bundle, first)
    assert exchange_hash(first) == digest

    nudged = copy.deepcopy(tiny_bundle.designs)
    export = nudged["t1"]
    design = export.design.copy()
    design[0, 0] += 1.0e-12
    nudged["t1"] = type(export)(
        spec=export.spec,
        design=design,
        deaths=export.deaths,
        offset=export.offset,
        s_age=export.s_age,
        s_year=export.s_year,
        n_tensor=export.n_tensor,
        factors=export.factors,
    )
    second = tmp_path / "b"
    other = write_exchange(
        type(tiny_bundle)(
            case=tiny_bundle.case, seed=tiny_bundle.seed, designs=nudged, cells=tiny_bundle.cells
        ),
        second,
    )
    assert other != digest


def test_a_missing_exchange_file_is_refused_rather_than_hashed_around(
    tmp_path, tiny_bundle
) -> None:
    """A hash over whatever files happen to be present would certify a partial export."""
    out = tmp_path / "partial"
    write_exchange(tiny_bundle, out)
    (out / "manifest.json").unlink()
    with pytest.raises(PolarisValidationError, match=r"missing manifest\.json"):
        exchange_hash(out)


def test_an_unknown_schema_version_is_refused(tmp_path, tiny_bundle) -> None:
    out = tmp_path / "future"
    write_exchange(tiny_bundle, out)
    manifest = json.loads((out / "manifest.json").read_text())
    manifest["schema_version"] = SCHEMA_VERSION + 1
    (out / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(PolarisValidationError, match="schema version"):
        read_exchange(out)


def test_the_manifest_records_the_one_r_setting_that_is_load_bearing(tmp_path, tiny_bundle) -> None:
    """``scalePenalty = FALSE`` travels in the manifest, as a version tripwire.

    Written when the setting was believed load-bearing. **The 2026-08-10 run measured it as
    a no-op on the ``paraPen`` path** (ADR-189 amendment 1): ``gam.setup`` passes
    ``scale.penalty`` only into ``smoothCon()``, and with penalties mismatched by ``1e6``
    at fixed λ the coefficients are bit-identical either way. ``sp`` already multiplies the
    supplied ``S`` directly and the guarantee is structural.

    The assertion stands, with a smaller claim behind it: a future ``mgcv`` that *did* route
    rescaling through ``paraPen`` would silently change what the comparison means, and the
    requirement living in the manifest rather than only in an R comment is what catches it.
    """
    out = tmp_path / "manifest"
    write_exchange(tiny_bundle, out)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["r_requirements"]["gam_control_scalePenalty"] is False
    assert manifest["r_requirements"]["method"] == "REML"
    assert manifest["r_requirements"]["family"] == "poisson"


def test_the_export_is_reproducible_from_its_pinned_seed(tmp_path) -> None:
    """Two exports produce byte-identical files — no wall clock anywhere (ADR-074)."""
    one = write_exchange(
        build_exchange("tiny", designs=_TINY, conformance_cells=_TINY_CELLS), tmp_path / "1"
    )
    two = write_exchange(
        build_exchange("tiny", designs=_TINY, conformance_cells=_TINY_CELLS), tmp_path / "2"
    )
    assert one == two


# --------------------------------------------------------------------------- #
# The R-free correctness guarantee
# --------------------------------------------------------------------------- #


def test_the_exported_coefficients_sit_at_the_unique_penalized_maximiser(tiny_written) -> None:
    """The claim that makes this suite verifiable without R.

    ``Xᵀ(y - μ) - Sβ`` is the gradient of the penalized Poisson log-likelihood. It
    vanishes at the maximiser, and the maximiser is unique because a PSD penalty added to
    a strictly concave log-likelihood is still strictly concave. So a near-zero norm
    proves the exported coefficients are what **any** conformant solver must return —
    which is exactly the correct-by-construction argument ADR-151 makes for the
    unpenalized case, extended by one term.
    """
    _, _, results = tiny_written
    for result in results:
        assert result.penalized_score_inf_norm < _SCORE_CEILING, result.name


def test_the_score_reduces_to_adr_151s_at_zero_penalty() -> None:
    """At ``S = 0`` the penalized score is the unpenalized one, so the two agree exactly.

    Not a formality: it pins the sign and the placement of the ``- Sβ`` term against an
    independently-tested function rather than against this module's own arithmetic.
    """
    from polaris_re.analytics.experience_oracle import (
        build_oracle_case,
        poisson_score_infinity_norm,
    )

    case = build_oracle_case(age_varying=False)
    zero = np.zeros((case.n_params, case.n_params), dtype=np.float64)
    penalized = penalized_score_infinity_norm(
        case.design, case.deaths, case.offset, case.python_coef, zero
    )
    assert penalized == pytest.approx(poisson_score_infinity_norm(case), rel=0.0, abs=0.0)


@pytest.mark.parametrize("nudge", [1.0e-3, -1.0e-3])
def test_the_score_norm_rises_when_the_coefficients_are_moved_off_the_maximiser(nudge) -> None:
    """Two-sided by construction: a norm that is near zero everywhere measures nothing."""
    spec = _TINY[0]
    cells = synthetic_cells()
    model = PenalizedTensorMIModel(
        cells, k_age=spec.k_age, k_year=spec.k_year, lambda_age=100.0, lambda_year=10.0
    )
    fit = model.fit()
    context = model.design_context
    assert context is not None
    penalty = np.zeros((fit.n_coef, fit.n_coef), dtype=np.float64)
    penalty[: context.n_tensor, : context.n_tensor] = 100.0 * context.s_age + 10.0 * context.s_year
    at_optimum = penalized_score_infinity_norm(
        context.design, context.deaths, context.offset, fit.coef, penalty
    )
    moved = penalized_score_infinity_norm(
        context.design, context.deaths, context.offset, fit.coef + nudge, penalty
    )
    assert at_optimum < _SCORE_CEILING < moved


# --------------------------------------------------------------------------- #
# The Python reference
# --------------------------------------------------------------------------- #


def test_the_reference_carries_the_covariance_unscaled_by_the_dispersion(tiny_written) -> None:
    """``mgcv``'s ``poisson()`` holds the scale at 1; our fit carries a quasi-Poisson φ̂.

    Comparing the shipped ``cov`` against ``vcov(m)`` would report a disagreement of
    exactly φ̂ and say nothing about either implementation, so the covariance travels
    unscaled and the dispersion travels as its own number. This asserts the arithmetic
    that keeps those two apart.
    """
    out, _, results = tiny_written
    payload = json.loads((out / "python_reference.json").read_text())["cells"]
    fixed = next(r for r in results if r.name == "fixed")
    assert fixed.dispersion != pytest.approx(1.0, abs=1.0e-3), (
        "a fixture whose dispersion is 1.0 cannot detect a scaling mistake"
    )
    exported = np.asarray(payload["fixed"]["vcov_unscaled"], dtype=np.float64)

    spec = _TINY[0]
    model = PenalizedTensorMIModel(
        synthetic_cells(), k_age=spec.k_age, k_year=spec.k_year, lambda_age=100.0, lambda_year=10.0
    )
    fit = model.fit()
    np.testing.assert_allclose(exported, fit.cov / fit.dispersion, rtol=1e-12, atol=0.0)
    assert payload["fixed"]["dispersion"] == pytest.approx(fit.dispersion, rel=1e-12)


def test_the_reference_ships_matrices_only_where_the_comparison_is_exact(tiny_written) -> None:
    """Full ``vcov`` at fixed λ; diagonals elsewhere — the size/diagnostic trade, asserted.

    ``mgcv`` forms ``Vc`` only when ``sp`` was estimated, and at free ``sp`` the two sides
    select different λ, so the full matrices are not comparable there. Shipping them
    anyway would inflate a committed golden to compute one ratio.
    """
    out, _, _ = tiny_written
    payload = json.loads((out / "python_reference.json").read_text())["cells"]
    assert payload["fixed"]["vcov_unscaled"] is not None
    assert payload["fixed"]["vcov_diag"] is not None
    # A fixed-lambda cell has no unconditional covariance on either side.
    assert payload["fixed"]["vcov_unconditional_diag"] is None
    # A cell that does not ask for level 4 carries no covariance at all.
    assert payload["fixed-factors"]["vcov_unscaled"] is None


def test_the_factor_block_edf_closes_in_the_exported_reference(tiny_written) -> None:
    """Anchor 4's additivity, on the exported numbers rather than on the fit object.

    The split is the half of Anchor 4 the amendment is actually about, and the export is
    where a block-boundary mistake would land: the tensor columns come first, the factor
    dummies after, and ``edf_tensor + edf_factors == edf_total`` is what tells R's
    per-coefficient ``m$edf`` where to be cut.
    """
    _, _, results = tiny_written
    with_factors = next(r for r in results if r.name == "fixed-factors")
    assert with_factors.edf_factors > 0.0, "the fixture must HAVE a factor block"
    assert with_factors.edf_tensor + with_factors.edf_factors == pytest.approx(
        with_factors.edf_total, rel=1e-12
    )


# --------------------------------------------------------------------------- #
# The comparator: it must pass on agreement AND fail on disagreement
# --------------------------------------------------------------------------- #


def test_the_comparator_passes_on_a_reference_that_agrees(tiny_written) -> None:
    out, _, _ = tiny_written
    ours = json.loads((out / "python_reference.json").read_text())
    comparison = compare_reference(out, ours, _mirror_as_mgcv(ours))
    assert comparison.passed
    assert comparison.mgcv_version == "1.9-1"
    assert comparison.levels_settled() == {1: True, 3: True, 4: True}
    assert any(c.checks for c in comparison.cells), "a comparison with no checks is vacuous"


@pytest.mark.parametrize(
    ("field", "factor", "metric"),
    [
        ("coef", 1.0e-3, "max_abs_coef_diff"),
        ("edf_total", 1.0, "abs_edf_total_diff"),
        ("edf_tensor", 1.0, "abs_edf_tensor_diff"),
        ("edf_factors", 1.0, "abs_edf_factors_diff"),
        ("vcov_unscaled", 1.0e-2, "max_rel_vcov_diff"),
    ],
)
def test_the_comparator_fails_on_a_seeded_disagreement(tiny_written, field, factor, metric) -> None:
    """Every tolerance is shown to bite. A comparator that cannot fail is not a check.

    The perturbations are seeded rather than random and sized to sit **above** the
    tolerance under test — the point is that the named metric is the one that fails, not
    merely that something did.
    """
    out, _, _ = tiny_written
    ours = json.loads((out / "python_reference.json").read_text())
    theirs = _mirror_as_mgcv(ours)
    cell = "fixed"
    value = theirs["cells"][cell][field]
    if isinstance(value, list):
        scale = float(np.max(np.abs(np.asarray(value, dtype=np.float64)))) or 1.0
        bumped = np.asarray(value, dtype=np.float64) + factor * scale
        theirs["cells"][cell][field] = bumped.tolist()
    else:
        theirs["cells"][cell][field] = float(value) + factor

    comparison = compare_reference(out, ours, theirs)
    assert not comparison.passed
    failed = {c.metric for cell_cmp in comparison.cells for c in cell_cmp.checks if not c.passed}
    assert metric in failed, f"expected {metric} to fail, got {sorted(failed)}"


def test_a_coefficient_difference_inside_the_null_space_still_moves_eta(tiny_written) -> None:
    """Level 1 has two metrics because they fail on different things.

    ``eta`` is invariant to the coefficient rattle a saturating penalty leaves in its own
    null space, which is why it carries the tighter tolerance; a difference big enough to
    move the fitted values must break BOTH. This asserts the pair behaves that way rather
    than trusting that two tolerances on the same vector are two checks.
    """
    out, _, _ = tiny_written
    ours = json.loads((out / "python_reference.json").read_text())
    theirs = _mirror_as_mgcv(ours)
    theirs["cells"]["fixed"]["coef"] = [c + 1.0e-3 for c in theirs["cells"]["fixed"]["coef"]]
    comparison = compare_reference(out, ours, theirs)
    failed = {c.metric for cell in comparison.cells for c in cell.checks if not c.passed}
    assert {"max_abs_coef_diff", "max_abs_eta_diff"} <= failed


def test_the_comparator_refuses_a_reference_from_a_different_exchange(
    tmp_path, tiny_written
) -> None:
    """The worst failure mode available here: parity declared against a file R never saw.

    Silent by nature — the numbers still look like numbers — so the hash guard runs first
    and unconditionally, before any metric is computed.
    """
    out, _, _ = tiny_written
    ours = json.loads((out / "python_reference.json").read_text())
    theirs = _mirror_as_mgcv(ours)
    theirs["exchange_sha256"] = "0" * 64
    with pytest.raises(PolarisValidationError, match="never saw"):
        compare_reference(out, ours, theirs)


def test_the_comparator_refuses_when_the_exchange_changed_underneath_it(
    tmp_path, tiny_bundle
) -> None:
    """The realistic version of the same failure: the export was re-run after R was."""
    out = tmp_path / "moved"
    digest = write_exchange(tiny_bundle, out)
    results = python_reference(tiny_bundle)
    write_python_reference(results, out, exchange_digest=digest, case="tiny")
    ours = json.loads((out / "python_reference.json").read_text())
    theirs = _mirror_as_mgcv(ours)
    # A one-character edit to a design file, of the kind a re-export could produce.
    target = out / "design_t1.tsv"
    lines = target.read_text().splitlines()
    lines[1] = lines[1].replace("\t", "\t0\t", 1)
    target.write_text("\n".join(lines) + "\n")
    with pytest.raises(PolarisValidationError, match="now hashes to"):
        compare_reference(out, ours, theirs)


def test_the_comparator_refuses_a_partial_r_run(tiny_written) -> None:
    """A batch that died halfway is a finding, not a comparison over what survived."""
    out, _, _ = tiny_written
    ours = json.loads((out / "python_reference.json").read_text())
    theirs = _mirror_as_mgcv(ours)
    theirs["cells"].pop("fixed-factors")
    with pytest.raises(PolarisValidationError, match="present on one side only"):
        compare_reference(out, ours, theirs)


def test_the_comparator_refuses_a_reference_that_fit_a_different_design(tiny_written) -> None:
    """Different coefficient counts mean the two sides did not share a design at all."""
    out, _, _ = tiny_written
    ours = json.loads((out / "python_reference.json").read_text())
    theirs = _mirror_as_mgcv(ours)
    theirs["cells"]["fixed"]["coef"] = theirs["cells"]["fixed"]["coef"][:-1]
    with pytest.raises(PolarisValidationError, match="same design"):
        compare_reference(out, ours, theirs)


def test_every_metric_carries_a_tolerance_and_a_stated_reason() -> None:
    """A tolerance without a rationale is a number somebody will later tune to pass.

    ADR-188's gate failed and the plan's response was explicitly *not* to move a
    threshold. The same discipline applies here: the report prints each tolerance's
    reason, so a future change to one is visible as a change to an argument.
    """
    assert LEVEL_METRICS
    seen = set()
    for spec in LEVEL_METRICS:
        assert spec.metric not in seen, f"duplicate metric {spec.metric}"
        seen.add(spec.metric)
        assert spec.level in {1, 2, 3, 4, 5}
        assert spec.tolerance > 0.0
        assert len(spec.rationale) > 80, spec.metric


def test_the_report_states_every_tolerance_and_names_the_exchange(tiny_written) -> None:
    """The committed artefact carries derived scalars only — never cell-grain experience.

    That is what lets the HMD/ILEC comparison be committed while their exchange stays in
    the maintainer's working directory (`DATA_LICENSING.md` §1).
    """
    out, digest, _ = tiny_written
    ours = json.loads((out / "python_reference.json").read_text())
    markdown = render_comparison_markdown(compare_reference(out, ours, _mirror_as_mgcv(ours)))
    assert digest in markdown
    assert "ALL LEVELS AGREE" in markdown
    for spec in LEVEL_METRICS:
        assert f"`{spec.metric}`" in markdown
    # No raw cell measures anywhere in the report.
    for forbidden in ("death_count", "central_exposure", "attained_age"):
        assert forbidden not in markdown


# --------------------------------------------------------------------------- #
# The committed synthetic exchange: is it the one this code produces?
# --------------------------------------------------------------------------- #


def test_the_committed_exchange_matches_its_recorded_hash() -> None:
    """Staleness guard. The exchange is a golden and the hash is what certifies it."""
    recorded = (COMMITTED_EXCHANGE / "exchange.sha256").read_text().strip()
    assert exchange_hash(COMMITTED_EXCHANGE) == recorded


def test_the_committed_exchange_is_what_this_code_exports(tmp_path) -> None:
    """Regenerate the inputs and compare — the guard against a drifted design.

    Cheap on purpose: the exchange depends on the designs and the penalties, **not** on λ
    selection, so regenerating it costs three unpenalized fits rather than the ~800 the
    reference costs. The reference's own regeneration is the test below.
    """
    fresh = write_exchange(build_exchange(), tmp_path / "fresh")
    assert fresh == (COMMITTED_EXCHANGE / "exchange.sha256").read_text().strip(), (
        "The committed exchange is stale: re-run "
        "`uv run python scripts/export_mgcv_case.py --case synthetic "
        "-o data/mgcv_exchange/synthetic`. An mgcv reference produced from the old one "
        "will be refused by the comparator's hash guard."
    )


def test_the_committed_reference_is_stamped_with_the_committed_exchange() -> None:
    """A reference that names a different exchange is unusable and must not be committed."""
    payload = json.loads((COMMITTED_EXCHANGE / "python_reference.json").read_text())
    assert payload["exchange_sha256"] == exchange_hash(COMMITTED_EXCHANGE)
    assert payload["case"] == "synthetic"
    assert payload["side"] == "python"
    assert set(payload["cells"]) == {c.name for c in CONFORMANCE_CELLS}


def test_no_committed_cell_selects_a_lambda_on_the_search_bound() -> None:
    """A degenerate conformance cell would make level 2 meaningless.

    **Measured, and it is why the synthetic grid is what it is:** at a 2-year age step
    both penalties saturate at 1e8 and ``edf_total`` lands on exactly 4.000, the
    dimension of the bilinear null space the two second-difference penalties share.
    Level 2 would then compare a bounded grid against an unbounded optimiser on a problem
    where the data identify neither λ. This test is what stops that from creeping back in
    the next time the fixture is touched.
    """
    payload = json.loads((COMMITTED_EXCHANGE / "python_reference.json").read_text())["cells"]
    free = {name: cell for name, cell in payload.items() if cell["free_sp"]}
    assert free, "the matrix must contain free-sp cells for levels 2 and 5"
    for name, cell in free.items():
        assert not cell["lambda_at_bound"], name
        # 4.0 is the bilinear null space; a fit sitting on it has selected away all
        # curvature and cannot distinguish two implementations of the criterion.
        assert cell["edf_total"] > 5.0, f"{name} edf_total={cell['edf_total']}"


def test_the_committed_reference_is_at_the_penalized_maximiser() -> None:
    """The R-free guarantee, asserted on the committed golden rather than a fixture."""
    payload = json.loads((COMMITTED_EXCHANGE / "python_reference.json").read_text())["cells"]
    for name, cell in payload.items():
        assert cell["penalized_score_inf_norm"] < _SCORE_CEILING, name


def test_the_committed_reference_is_what_this_code_computes() -> None:
    """The other half of the staleness guard — the fits, not just the design.

    **Not marked ``@slow``, deliberately.** It is ~800 penalized fits, which sounds like
    a candidate; measured, the whole thing is ~4 s on this fixture, and a staleness guard
    excluded from ``make test`` is a guard that fires the day after it was needed. If a
    later fixture makes this expensive, split it rather than mark it.

    Compared with a tolerance rather than bit-for-bit: λ selection is a deterministic
    grid (ADR-186) so the selected λ must match exactly, while the fitted coefficients
    ride a parallel reduction whose rounding ties can flip (ADR-184 amendment 2).
    """
    bundle = read_exchange(COMMITTED_EXCHANGE)
    committed = json.loads((COMMITTED_EXCHANGE / "python_reference.json").read_text())["cells"]
    for result in python_reference(bundle):
        recorded = committed[result.name]
        assert recorded["sp"] == [result.lambda_age, result.lambda_year], result.name
        np.testing.assert_allclose(
            np.asarray(recorded["coef"], dtype=np.float64), result.coef, rtol=1e-9, atol=1e-12
        )
        assert recorded["edf_total"] == pytest.approx(result.edf_total, rel=1e-9)


# --------------------------------------------------------------------------- #
# The R path is gated, and the R script is syntactically what it claims to be
# --------------------------------------------------------------------------- #


def test_the_r_path_is_gated_so_ci_never_grows_an_r_dependency() -> None:
    """ADR-151's Anchor-5 discipline, over a subprocess rather than ``rpy2``.

    The conformance R script is a standalone ``Rscript`` program precisely so a
    maintainer needs no Python-R bridge; the gate therefore probes ``Rscript`` on PATH
    rather than importing anything.
    """
    assert isinstance(rscript_mgcv_available(), bool)


def test_the_r_script_declares_the_load_bearing_settings_it_must_use() -> None:
    """A grep-level check on the R side, which no Python test can otherwise reach.

    ADR-186 amendment 2's lesson — *grep the claim set before calling a fix done* —
    applied to a file in another language: the three settings the construction depends on
    are asserted to be present, so a future edit that drops one fails here rather than in
    a maintainer's R session two sessions later.
    """
    source = (REPO_ROOT / "scripts" / "mgcv_conformance.R").read_text()
    assert "scalePenalty" in source, "sp must multiply the supplied S directly"
    assert "gam_control_scalePenalty" in source, "the requirement travels in the manifest"
    assert 'method = "REML"' in source
    assert "paraPen" in source, "our design and our penalties, not a te()"
    assert "digits = NA" in source, "full precision, or level 1 is a formatting artefact"
    assert "quit(status = status)" in source, "a dead batch must not exit 0"
    assert "m$Vc" in source, "Vc's presence is tested, not vcov()'s success"
    assert 'matrix = "rowmajor"' in source, (
        "the Python side reads each vcov as a list of ROWS; these matrices are symmetric, "
        "so a column-major dump would not show up here — which is why it is pinned"
    )
    # The three surviving guards around `scalePenalty`. It was believed load-bearing when
    # these were written; the 2026-08-10 run measured it as a **no-op on the paraPen path**
    # (ADR-189 amendment 1), so they are a version tripwire rather than what makes the
    # comparison valid. The assertions stand: a tripwire that silently stopped being set
    # would still be worth failing on.
    assert "penalty_scaling" in source, (
        "the probe is kept as a tripwire even though the run showed it cannot currently "
        "fire — m$paraPen$S.scale is absent and length(m$smooth) is 0"
    )
    assert "sp_supplied" in source, "what R was asked for travels beside what it reports"
    assert "scale_penalty = scale_penalty" in source, (
        "the value actually used is recorded, not a literal that could drift from it"
    )
    # Read the field DIRECTLY, not through isFALSE(): isFALSE(NULL) is FALSE, so an
    # absent field under a negation would hand mgcv its rescaling default without the
    # tryCatch firing (PR #192 review [P2]).
    assert "isFALSE(manifest" not in source, (
        "a missing manifest field must be refused, not coerced into the unsafe direction"
    )
    assert "no usable r_requirements$gam_control_scalePenalty" in source, (
        "and the refusal must name the field and the re-export, at the point of the mistake"
    )


def test_the_comparator_refuses_a_run_with_mgcvs_penalty_rescaling_left_on(tiny_written) -> None:
    """The second unconditional guard, alongside the hash.

    A run with rescaling ON compared a rescaled penalty against ours, so `sp` did not
    multiply the same matrix on the two sides and every fixed-lambda metric would disagree
    for a reason that is not arithmetic. Refused rather than annotated, because an
    annotated false finding still costs a round trip to chase.
    """
    out, _, _ = tiny_written
    ours = json.loads((out / "python_reference.json").read_text())
    theirs = _mirror_as_mgcv(ours)
    theirs["scale_penalty"] = True
    with pytest.raises(PolarisValidationError, match="scale_penalty"):
        compare_reference(out, ours, theirs)


def test_the_comparator_refuses_a_fixed_cell_r_fit_at_the_wrong_lambda(tiny_written) -> None:
    """`sp_supplied` exists so a fixed-lambda comparison cannot silently be at another λ."""
    out, _, _ = tiny_written
    ours = json.loads((out / "python_reference.json").read_text())
    theirs = _mirror_as_mgcv(ours)
    theirs["cells"]["fixed"]["sp_supplied"] = [1.0, 1.0]
    with pytest.raises(PolarisValidationError, match="is not a comparison"):
        compare_reference(out, ours, theirs)


def test_penalty_scaling_artefacts_are_surfaced_as_a_note(tiny_written) -> None:
    """Present-and-non-trivial is a finding; absent proves nothing and must not read as pass."""
    out, _, _ = tiny_written
    ours = json.loads((out / "python_reference.json").read_text())
    theirs = _mirror_as_mgcv(ours)
    theirs["cells"]["fixed"]["penalty_scaling"] = {"S_scale": [3.0, 0.5]}
    comparison = compare_reference(out, ours, theirs)
    notes = [n for cell in comparison.cells for n in cell.notes]
    assert any("penalty-scaling artefacts" in n for n in notes)
    # Surfacing is not gating — the numeric metrics still decide pass/fail.
    assert comparison.passed


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_r_script_runs_end_to_end_and_agrees(tmp_path, tiny_bundle) -> None:  # pragma: no cover
    """The real conformance run, when R happens to be present.

    Skipped in CI and in the Docker image by design. On a maintainer's machine it is the
    whole slice in one test — and a **failure here is a result**, per PLAN Anchor 8: a
    conformance run that refutes ``tr(F)`` changes Anchor 4 rather than failing the slice.
    """
    out = tmp_path / "r-run"
    digest = write_exchange(tiny_bundle, out)
    write_python_reference(python_reference(tiny_bundle), out, exchange_digest=digest, case="tiny")
    done = subprocess.run(
        [
            "Rscript",
            str(REPO_ROOT / "scripts" / "mgcv_conformance.R"),
            str(out),
            str(out / "mgcv_reference.json"),
        ],
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    comparison = compare_reference(
        out,
        json.loads((out / "python_reference.json").read_text()),
        json.loads((out / "mgcv_reference.json").read_text()),
    )
    print(render_comparison_markdown(comparison))
    assert comparison.passed, "levels: " + repr(comparison.levels_settled())


def test_the_exporter_refuses_to_commit_real_data(tmp_path) -> None:
    """`DATA_LICENSING.md` §1 asserted at the CLI boundary, not in a docstring.

    A real-data exchange is cell-grain experience. The exporter demands an explicit
    output path for those cases rather than defaulting into the repository, because the
    default is exactly how a licensing boundary gets crossed by accident.
    """
    script = REPO_ROOT / "scripts" / "export_mgcv_case.py"
    frame = pl.DataFrame({"attained_age": [45], "calendar_year": [2012], "q_base": [0.004]})
    cells_path = tmp_path / "cells.parquet"
    frame.write_parquet(cells_path)
    done = subprocess.run(
        [sys.executable, str(script), "--case", "ilec-banded", "--cells", str(cells_path)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 1
    assert "OUTSIDE the repository" in done.stderr


def test_the_exporter_refuses_a_supplied_frame_for_the_synthetic_case(tmp_path) -> None:
    """The committed case must stay reproducible from its seed, or it is not verifiable."""
    script = REPO_ROOT / "scripts" / "export_mgcv_case.py"
    done = subprocess.run(
        [
            sys.executable,
            str(script),
            "--case",
            "synthetic",
            "--cells",
            str(tmp_path / "whatever.parquet"),
            "-o",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 1
    assert "refused for the synthetic case" in done.stderr


def test_the_real_data_path_exports_from_a_supplied_cells_file(tmp_path) -> None:
    """The `--cells` route, exercised on a frame this container can actually produce.

    The real-data cases cannot be tested against real data here — HMD and ILEC are not in
    the container and their exchange must never be committed. What *can* be tested is the
    path itself: read a grouped-cells file, build every design over it, and record in the
    manifest which factor columns each design actually found. The frame below goes through
    `attach_empirical_base` exactly as the runbook's snippet does, so the contract the
    snippet promises is the contract the test asserts.
    """
    from polaris_re.analytics.experience_diligence import attach_empirical_base

    raw = synthetic_cells(with_factor=True).drop("q_base")
    base = attach_empirical_base(raw, exposure_col="central_exposure", deaths_col="death_count")
    cells_path = tmp_path / "cells.parquet"
    base.cells.write_parquet(cells_path)

    out = tmp_path / "local-exchange"
    done = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "export_mgcv_case.py"),
            "--case",
            "ilec-banded",
            "--cells",
            str(cells_path),
            "-o",
            str(out),
            "--no-python-reference",
        ],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert done.returncode == 0, done.stderr + done.stdout
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["case"] == "ilec-banded"
    # Every design sees the same supplied frame, so the factor block is whatever that
    # frame carries — recorded per design rather than assumed from the design's own flag.
    assert all(meta["factors"] == ["sex"] for meta in manifest["designs"].values())
    assert exchange_hash(out) == (out / "exchange.sha256").read_text().strip()
    assert not (out / "python_reference.json").exists()


def test_a_cells_file_without_a_base_rate_is_refused_with_the_reason(tmp_path) -> None:
    """`q_base` missing is the likely mistake, so the message names the step that adds it.

    A frame straight out of `load_ilec` has exposure and deaths but no base rate; feeding
    it here would fail several frames deep inside the model's own validation.
    """
    cells_path = tmp_path / "no_base.parquet"
    synthetic_cells().drop("q_base").write_parquet(cells_path)
    done = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "export_mgcv_case.py"),
            "--case",
            "hmd-usa",
            "--cells",
            str(cells_path),
            "-o",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 1
    assert "attach_empirical_base()" in done.stderr


def test_the_formula_probe_uses_the_same_difference_step_as_the_python_side() -> None:
    """`ks_formula_probe.R` hardcodes `KS_LOG_STEP` across a language boundary.

    ADR-190's decisive comparison only means anything if both sides difference over the
    same step: the probe builds `J` from `mgcv`'s coefficients and we build ours from
    `smoothing_uncertainty`, and a step mismatch would compare two different quantities
    while still printing a ratio. The R script cannot import `KS_LOG_STEP`, and the
    manifest cannot carry it without re-exporting the hash-guarded exchange and
    invalidating the committed Python reference — a large change to pin a small constant.
    So the coupling is pinned here instead, which is the same device the suite already
    uses for `scripts/mgcv_conformance.R`. PR #195 review [P2].
    """
    source = (REPO_ROOT / "scripts" / "ks_formula_probe.R").read_text()

    match = re.search(r"^h <- log\(10\) \* ([0-9.]+)$", source, re.MULTILINE)
    assert match is not None, (
        "could not find the `h <- log(10) * <refine_step>` line in ks_formula_probe.R; if "
        "the step moved, this test must move with it rather than be deleted"
    )
    assert float(match.group(1)) == REFINE_STEP, (
        f"ks_formula_probe.R differences over log(10) * {match.group(1)} but Python's "
        f"KS_LOG_STEP is log(10) * {REFINE_STEP}. The probe and `smoothing_uncertainty` "
        f"would be measuring different quantities, and ADR-190's ratio would be comparing "
        f"a central difference at one step against one at another."
    )
    np.testing.assert_allclose(
        float(np.log(10.0)) * float(match.group(1)), KS_LOG_STEP, rtol=0.0, atol=0.0
    )
