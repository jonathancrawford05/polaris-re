"""Slice 2's conformance module: the producer cannot see ``mgcv``'s Hessian, the
comparison reads the declared layout, and — when R is available — the Hessian
agrees with ``mgcv``'s own ``outer.info$hess`` (tier 1 only here; the committed
reading is CI's, on the pinned digest)."""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.gam_hessian_conformance import (
    HESSIAN_AGREEMENT_TOL,
    HESSIAN_CLAIM,
    RHessianPayload,
    compare_hessian_case,
    hessian_at_recipe,
    recipe_of,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]


def _synthetic_payload(
    family: str, link: str, free_scale: bool
) -> tuple[RHessianPayload, np.ndarray, tuple]:
    """A self-contained payload whose 'mgcv' Hessian is a placeholder — enough to
    exercise the producer's signature and the layout reader, not parity."""
    rng = np.random.default_rng(3)
    n, p = 120, 6
    t = np.linspace(-1.0, 1.0, n)
    x = np.column_stack([np.ones(n), t, t**2, t**3, np.sin(t), np.cos(t)])
    d = np.diff(np.eye(p), n=2, axis=0)
    s1 = d.T @ d
    s2 = np.zeros((p, p))
    s2[1, 1] = 1.0
    y = rng.poisson(np.exp(0.3 + 0.4 * t)).astype(float)
    m = 2
    dim = m + 1 if free_scale else m
    payload = RHessianPayload(
        label="synthetic",
        family=family,
        link=link,
        y=y.tolist(),
        prior_weights=[1.0] * n,
        selected_sp=[5.0, 50.0],
        outer_hessian=np.eye(dim).ravel().tolist(),
        hess_dim=dim,
        scale=1.0,
        scale_estimated=free_scale,
    )
    return payload, x, (s1, s2)


def test_the_producer_is_handed_a_recipe_with_no_reference_keys() -> None:
    payload, _x, _pens = _synthetic_payload("poisson", "log", False)
    recipe = recipe_of(payload)
    assert set(recipe) == {"label", "family", "link", "y", "prior_weights", "selected_sp"}
    for forbidden in ("outer_hessian", "scale", "hess_dim", "outer_gradient"):
        assert forbidden not in recipe


def test_producer_output_is_independent_of_the_reference_hessian() -> None:
    payload, x, pens = _synthetic_payload("poisson", "log", False)
    a = hessian_at_recipe(recipe_of(payload), x, pens).hessian
    payload["outer_hessian"] = (np.eye(2) * 99.0).ravel().tolist()
    b = hessian_at_recipe(recipe_of(payload), x, pens).hessian
    np.testing.assert_array_equal(a, b)


def test_the_declared_claim_is_parity_evidence_for_both_quantities() -> None:
    require_parity_evidence(HESSIAN_CLAIM.quantities, claim="exact Hessian vs mgcv")


def test_free_scale_layout_is_schur_reduced_and_a_bad_layout_is_refused() -> None:
    payload, x, pens = _synthetic_payload("quasipoisson", "log", True)
    full = np.array([[2.0, 0.1, 1.0], [0.1, 3.0, 0.5], [1.0, 0.5, 10.0]])
    payload["outer_hessian"] = full.ravel().tolist()
    cmp = compare_hessian_case(payload, x, pens)
    expected = full[:2, :2] - full[:2, 2:] @ full[2:, 2:] ** -1 @ full[2:, :2]
    np.testing.assert_allclose(cmp.mgcv, expected)
    payload["hess_dim"] = 5
    payload["outer_hessian"] = np.eye(5).ravel().tolist()
    with pytest.raises(PolarisValidationError, match="expected 2 or 3"):
        compare_hessian_case(payload, x, pens)


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="needs R with mgcv")
def test_the_exact_hessian_agrees_with_mgcvs_outer_hessian(tmp_path: Path) -> None:
    out = tmp_path / "hess.json"
    run = subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_hessian_probe.R"), str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != 0 or not out.exists():
        pytest.skip(f"R/mgcv unavailable: {run.stderr[-200:]}")
    probe = json.loads(out.read_text())
    design = np.asarray(probe["design"], dtype=np.float64)
    pens = tuple(np.asarray(b, dtype=np.float64) for b in probe["penalties"])
    assert set(probe["cases"]) == {
        "poisson-log",
        "binomial-logit",
        "binomial-cloglog",
        "quasipoisson-log",
        "gaussian-identity",
    }
    for label, case in probe["cases"].items():
        cmp = compare_hessian_case(case, design, pens)
        assert cmp.max_scaled_diff < HESSIAN_AGREEMENT_TOL, label
        assert cmp.agrees, label
