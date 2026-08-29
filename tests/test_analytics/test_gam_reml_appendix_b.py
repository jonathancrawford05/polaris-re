"""``docs/PLAN_mgcv_parity_engine.md`` slice 5c — Wood (2011) Appendix B.

R-free tests for :mod:`polaris_re.analytics.gam_reml_appendix_b`, per the
PLAN's sequencing step 2: "construction is verified before fit" (Anchor 1)
applied to a numerical algorithm rather than a basis — invariance,
known-rank exactness, agreement with the naive path where the naive path is
reliable, and insensitivity to a badly-scaled ``lambda`` where the naive path
is not.

**The mutation protocol lives in ``docs/DECISIONS.md``'s slice 5c ADR, not
here** — this file's classes ARE what the protocol names as "must be caught
by"; the ADR records, for each of the six mutations, which test below failed
and on which assertion.
"""

import numpy as np
import pytest
import scipy.linalg

from polaris_re.analytics.gam_model import assemble_model_design
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.analytics.gam_reml_appendix_b import (
    appendix_b_transform,
    logdet_s_plus,
)
from polaris_re.core.exceptions import PolarisValidationError


def _random_orthogonal(rng: np.random.Generator, n: int) -> np.ndarray:
    a = rng.normal(size=(n, n))
    q, r = np.linalg.qr(a)
    # Fix the sign ambiguity in QR so `q` is uniformly Haar-random, not that
    # it matters for the invariance test below — any orthogonal matrix works.
    return q * np.sign(np.diag(r))


def _naive_logdet_s_plus(blocks: tuple[np.ndarray, ...], lambdas: np.ndarray) -> float:
    """The shipped defect this module replaces: eigendecompose the SUM,
    cut at a fixed relative tolerance of ``1e-10``. Used here only as the
    "agrees where the naive path is reliable" reference (flat, well-scaled
    lambda), never as a correctness oracle for the spread-lambda case."""
    s = np.zeros_like(blocks[0])
    for lam, block in zip(lambdas, blocks, strict=True):
        s = s + lam * block
    eigenvalues = np.linalg.eigvalsh(s)
    largest = float(eigenvalues.max())
    positive = eigenvalues[eigenvalues > max(largest, 1e-300) * 1e-10]
    return float(np.sum(np.log(positive)))


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20260829)


def _second_difference_penalty(p: int) -> np.ndarray:
    """A standard rank-deficient penalty block: `d.T @ d` for a second
    difference operator has a 2-dimensional null space (constant and linear
    sequences), the same construction the existing REML tests already use."""
    d = np.diff(np.eye(p), n=2, axis=0)
    return d.T @ d


class TestKnownRankSynthetic:
    """Appendix B must recover a HAND-KNOWN rank exactly, deficient or not —
    the direct test of the algorithm's own purpose, independent of any
    lambda-scaling concern."""

    def test_two_disjoint_full_rank_blocks(self, rng: np.random.Generator) -> None:
        """Two blocks with disjoint column supports, both individually full
        rank on their own span — the ADR-196 fixture's own structure, where
        the naive cut and Appendix B must agree because there is no
        null-space ambiguity at all."""
        p1, p2 = 3, 4
        p = p1 + p2
        a = rng.normal(size=(p1, p1))
        s1 = np.zeros((p, p))
        s1[:p1, :p1] = a.T @ a + np.eye(p1)  # full rank, positive definite
        b = rng.normal(size=(p2, p2))
        s2 = np.zeros((p, p))
        s2[p1:, p1:] = b.T @ b + np.eye(p2)
        lambdas = np.array([2.0, 5.0])

        result = appendix_b_transform((s1, s2), lambdas)
        assert result.rank == p
        expected = np.linalg.slogdet(lambdas[0] * s1 + lambdas[1] * s2)[1]
        assert result.logdet_s_plus == pytest.approx(expected, rel=1e-9)

    def test_rank_deficient_second_difference_block(self) -> None:
        """A single second-difference penalty, `p=6`: exact rank `p - 2 = 4`
        by construction (the null space is {constants, linear sequences})."""
        p = 6
        s = _second_difference_penalty(p)
        assert np.linalg.matrix_rank(s) == p - 2  # sanity on the fixture itself

        result = appendix_b_transform((s,), np.array([3.0]))
        assert result.rank == p - 2
        eigenvalues = np.linalg.eigvalsh(3.0 * s)
        positive = np.sort(eigenvalues)[::-1][: p - 2]
        expected = float(np.sum(np.log(positive)))
        assert result.logdet_s_plus == pytest.approx(expected, rel=1e-9)

    def test_shared_null_space_across_two_blocks(self) -> None:
        """Both blocks are second-difference penalties on the SAME `p`
        columns (the `ti()`-sharing-a-span structure ADR-208 found the
        defect on, in miniature): individually rank `p-2`, and the model's
        TRUE null space is still exactly the shared {constants, linear}
        subspace (2-dimensional) for ANY positive combination — a case the
        pre-step (Section "S not formally full rank") exists for."""
        p = 6
        s1 = _second_difference_penalty(p)
        rng = np.random.default_rng(7)
        rotation = _random_orthogonal(rng, p)
        s2 = rotation @ s1 @ rotation.T  # same rank, different eigenvectors
        # Force an EXACT shared null space by re-deriving s2 from the same
        # null space as s1 instead (a rotated s1 would generally NOT share
        # s1's null space, which defeats the point of this fixture).
        null_space = scipy.linalg.null_space(s1)  # (p, 2)
        row_space = scipy.linalg.orth(s1)  # (p, p-2)
        a = rng.normal(size=(p - 2, p - 2))
        s2 = row_space @ (a.T @ a + np.eye(p - 2)) @ row_space.T
        assert np.allclose(s2 @ null_space, 0.0, atol=1e-10)

        result = appendix_b_transform((s1, s2), np.array([10.0**5, 10.0**-3]))
        assert result.rank == p - 2

    def test_full_rank_block(self, rng: np.random.Generator) -> None:
        """No null space at all: a positive-definite block on its own,
        `r == q` on the very first pre-step, exercising the immediate
        termination branch."""
        p = 5
        a = rng.normal(size=(p, p))
        s = a.T @ a + np.eye(p)
        result = appendix_b_transform((s,), np.array([4.0]))
        assert result.rank == p
        assert result.logdet_s_plus == pytest.approx(np.linalg.slogdet(4.0 * s)[1], rel=1e-9)


class TestOrthogonalInvariance:
    """``log|S|+`` must not depend on the coordinate system the blocks are
    expressed in — apply the SAME random orthogonal transform to every
    block simultaneously (a genuine change of basis for the whole model,
    unlike mutation 6's transposed `Q_s`, which is an INTERNAL bug that
    happens to also leave this quantity unchanged — see the ADR)."""

    def test_invariant_to_a_shared_orthogonal_transform(self, rng: np.random.Generator) -> None:
        p1, p2 = 4, 3
        p = p1 + p2
        a = rng.normal(size=(p1, p1))
        s1 = np.zeros((p, p))
        s1[:p1, :p1] = _second_difference_penalty(p1) if p1 > 2 else a.T @ a
        b = rng.normal(size=(p2, p2))
        s2 = np.zeros((p, p))
        s2[p1:, p1:] = b.T @ b + np.eye(p2)
        lambdas = np.array([1e4, 1e-2])

        baseline = logdet_s_plus((s1, s2), lambdas)

        q = _random_orthogonal(rng, p)
        rotated = (q @ s1 @ q.T, q @ s2 @ q.T)
        rotated_value = logdet_s_plus(rotated, lambdas)

        assert rotated_value == pytest.approx(baseline, rel=1e-8, abs=1e-8)


class TestAgreesWithNaiveAtFlatLambda:
    """Wood: "the problem vanishes for a full rank S1" and, more generally,
    for any well-scaled combination — where the naive cut IS reliable,
    Appendix B must reproduce it, not merely "a different but plausible"
    answer."""

    @pytest.mark.parametrize("log_lambda", [0.0, 2.0, 4.0, -1.0])
    def test_flat_lambda_matches_naive(self, log_lambda: float) -> None:
        p = 6
        s1 = _second_difference_penalty(p)
        s2 = np.eye(p) * 0.3  # a second, full-rank block sharing the span
        lambdas = np.array([10.0**log_lambda, 10.0**log_lambda])

        appendix_b_value = logdet_s_plus((s1, s2), lambdas)
        naive_value = _naive_logdet_s_plus((s1, s2), lambdas)
        assert appendix_b_value == pytest.approx(naive_value, abs=1e-6)


class TestUnaffectedBySpreadLambda:
    """The defect this module fixes: the naive cut's answer for
    `log|S|+ - (naive value at some lambda_0)` should be roughly constant
    only when the lambda's are flat. Appendix B's own value across a
    12-decade-spread must stay consistent with the FLAT baseline once the
    lambda-dependent scale factor is accounted for analytically — i.e. its
    departure from "what naive gives at a flat point, rescaled" must be
    far smaller than the naive method's own departure."""

    def test_spread_lambda_stays_close_to_the_flat_baseline_prediction(self) -> None:
        p = 6
        s1 = _second_difference_penalty(p)  # rank p-2
        s2 = np.eye(p) * 0.3  # rank p, shares the whole span with s1

        # At any lambda, the TRUE null space is empty (s2 alone is full
        # rank), so log|S|+ = log|lambda_1*s1 + lambda_2*s2| exactly — a
        # genuine `np.linalg.slogdet` is valid here as ground truth,
        # independent of both the naive cut and Appendix B.
        rng = np.random.default_rng(3)
        spreads = [(2.0, 2.0), (6.0, 6.0), (-1.0, 11.0), (11.0, -1.0), (4.0, 9.0)]
        for log_l1, log_l2 in spreads:
            lambdas = np.array([10.0**log_l1, 10.0**log_l2])
            ground_truth = np.linalg.slogdet(lambdas[0] * s1 + lambdas[1] * s2)[1]
            appendix_b_value = logdet_s_plus((s1, s2), lambdas)
            # A 12-decade lambda spread pushes `X'WX`-scale conditioning near
            # `cond ~ 1e12` even for a genuinely full-rank sum — double
            # precision (`eps ~2.2e-16`) itself is only good to
            # `~cond*eps ~2e-4` there, on EITHER side of this comparison
            # (slogdet included), so `rel=1e-6` would be asserting more
            # precision than IEEE 754 can supply, not testing the algorithm.
            assert appendix_b_value == pytest.approx(ground_truth, rel=2e-3), (
                f"Appendix B departed from the true (full-rank) determinant at "
                f"log10 lambda=({log_l1}, {log_l2})"
            )
        del rng  # fixture symmetry with the other test classes; unused here


class TestEReconstructsS:
    """``E^T @ E == S`` restricted to its positive eigenspace — tests the
    stable square root and the accumulated similarity transform `Q_s` ON
    THEIR OWN TERMS, per the PLAN: "log|S|+ is invariant to a transposed
    Q_s, so every determinant test passes under it. Only the
    E-transpose-E identity catches it." (mutation 6)."""

    @pytest.mark.parametrize(
        "blocks_and_lambdas",
        [
            pytest.param(
                (
                    (_second_difference_penalty(6), np.eye(6) * 0.3),
                    np.array([3.0, 5.0]),
                ),
                id="rank_deficient_plus_full_rank",
            ),
            pytest.param(
                ((_second_difference_penalty(6),), np.array([7.0])),
                id="single_rank_deficient_block",
            ),
        ],
    )
    def test_e_transpose_e_reconstructs_s_restricted_to_its_positive_part(
        self, blocks_and_lambdas: tuple[tuple[np.ndarray, ...], np.ndarray]
    ) -> None:
        blocks, lambdas = blocks_and_lambdas
        result = appendix_b_transform(blocks, lambdas)

        s_total = np.zeros_like(blocks[0])
        for lam, block in zip(lambdas, blocks, strict=True):
            s_total = s_total + lam * block

        reconstructed = result.e.T @ result.e
        # Project both onto the row space of S (the null space is discarded
        # by construction — E has no rows there) before comparing.
        eigenvalues, eigenvectors = np.linalg.eigh(s_total)
        positive_space = eigenvectors[:, eigenvalues > eigenvalues.max() * 1e-8]
        projector = positive_space @ positive_space.T
        s_projected = projector @ s_total @ projector

        assert reconstructed == pytest.approx(s_projected, abs=1e-6)
        assert result.e.shape == (result.rank, blocks[0].shape[0])

    def test_e_reconstructs_s_when_the_two_blocks_genuinely_separate(self) -> None:
        """The case above never actually exercises the accumulated
        similarity transform: at well-conditioned lambdas both blocks land
        in the SAME dominant set on the first pass (``_dominant_split``
        never separates them), so the loop terminates via the ``r == dim``
        branch on iteration 1 without ever touching the ``q_accum``
        bookkeeping mutation 6 corrupts — found by attempting the mutation
        protocol and discovering it passed silently.

        This case forces the two-iteration path: an EXTREME lambda ratio
        (dominant/subordinate `Omega` ratio ~1e-9, far below the cube-root-eps
        threshold) so block 1 alone is dominant on pass 1, with block 2 only
        entering on pass 2 — and a random rotation applied to BOTH blocks so
        the dominant block's own eigenvectors are not axis-aligned, making
        ``u_full`` genuinely asymmetric (``u_full.T != u_full``, unlike the
        axis-aligned construction above, where a transpose is invisible).
        Diagonal-in-the-unrotated-frame blocks keep the ground truth exact
        (no `eigh`-reconstruction noise at this lambda spread, unlike a
        badly-conditioned dense fixture) while still being a genuine
        separation case.
        """
        rng = np.random.default_rng(11)
        rotation = _random_orthogonal(rng, 6)
        block1_diag = np.diag([1.0, 1.0, 1.0, 1.0, 0.0, 0.0])  # rank 4
        block2_diag = np.diag([0.0, 0.0, 0.0, 0.0, 2.0, 2.0])  # complementary rank 2
        block1 = rotation @ block1_diag @ rotation.T
        block2 = rotation @ block2_diag @ rotation.T
        lambdas = np.array([1e8, 1.0])  # Omega ratio ~1e-9: genuine separation

        result = appendix_b_transform((block1, block2), lambdas)
        assert result.rank == 6  # the two blocks are jointly full rank

        s_total = 1e8 * block1 + 1.0 * block2
        # Exact ground truth: eigenvalues of s_total are exactly
        # {1e8 (x4), 2.0 (x2)} regardless of the rotation (a similarity
        # transform doesn't change eigenvalues), so both the determinant
        # and the reconstruction have a closed form immune to eigh noise.
        expected_logdet = 4.0 * np.log(1e8) + 2.0 * np.log(2.0)
        assert result.logdet_s_plus == pytest.approx(expected_logdet, rel=1e-9)

        reconstructed = result.e.T @ result.e
        assert reconstructed == pytest.approx(s_total, rel=1e-6, abs=1e-2)

    def test_e_reconstructs_s_on_the_target_models_own_four_blocks(self) -> None:
        """The real adversarial case, found only after the two hand-built
        fixtures above BOTH passed under mutation 6 (the axis-aligned one
        never separates; the shared-rotation one is accidentally
        simultaneously diagonalizable, which hides a transpose because
        every ``u_full`` this construction produces commutes with the
        resolved blocks in a way a generic interaction does not). Real
        penalty blocks from the target model's own four terms — a
        reference-age ``cr`` smooth, its numeric-``by`` scaling, and a
        ``ti()``'s two margins — have no such coincidental structure, and a
        transposed ``Q_s`` corrupts this reconstruction by ~100%
        (``max abs diff`` on the order of ``max abs S`` itself), not a
        rounding-level discrepancy. R-free: the design and penalty blocks
        are Python's own basis construction (:mod:`gam_model`), needing no
        ``mgcv`` call.
        """
        rng = np.random.default_rng(20260829)
        n = 300
        age_knots = (1.0, 2.0, 4.0, 7.0, 14.0, 18.0, 24.0, 35.0, 50.0, 70.0, 85.0, 90.0, 95.0)
        year_knots = (1.0, 2.0, 3.0, 5.0, 10.0, 21.0)
        model = _multiterm_model_spec(age_knots, year_knots)
        data = {
            "AttdAge": rng.uniform(1.0, 95.0, size=n),
            "PolYear": rng.uniform(1.0, 21.0, size=n),
            "StudyYear_C": rng.uniform(-5.0, 5.0, size=n),
        }
        design = assemble_model_design(model, data)
        blocks = tuple(design["penalty_blocks"])
        # The same 6.8-decade spread ADR-208's own conformance fixture hits
        # at mgcv's free-sp optimum — not an artificially extreme strawman.
        lambdas = np.array([10.0**6.8, 10.0**0.0, 10.0**3.3, 10.0**3.0])

        result = appendix_b_transform(blocks, lambdas)
        s_total = np.zeros_like(blocks[0])
        for lam, block in zip(lambdas, blocks, strict=True):
            s_total = s_total + lam * block

        reconstructed = result.e.T @ result.e
        assert reconstructed == pytest.approx(s_total, rel=1e-4, abs=1.0)


class TestValidation:
    def test_rejects_empty_blocks(self) -> None:
        with pytest.raises(PolarisValidationError, match="non-empty"):
            appendix_b_transform((), np.array([]))

    def test_rejects_mismatched_lambda_length(self) -> None:
        s = np.eye(3)
        with pytest.raises(PolarisValidationError, match="lambdas has shape"):
            appendix_b_transform((s,), np.array([1.0, 2.0]))

    def test_rejects_nonpositive_lambda(self) -> None:
        s = np.eye(3)
        with pytest.raises(PolarisValidationError, match="positive"):
            appendix_b_transform((s,), np.array([-1.0]))

    def test_rejects_mismatched_block_shapes(self) -> None:
        with pytest.raises(PolarisValidationError, match="square and equal-sized"):
            appendix_b_transform((np.eye(3), np.eye(4)), np.array([1.0, 1.0]))
