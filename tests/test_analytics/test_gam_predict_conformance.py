"""``gam_predict_conformance`` — preview epic Slice P1 (ADR-249).

R-free: the provenance gate (ADR-193) and the spec table. R-gated: the probe is
run and the comparison is read (tier 1 here — a regression check only; the
committed number is the tier-3 CI reading)."""

import copy
import json
import subprocess
import typing
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_predict_conformance import (
    PREDICT_CASE_NAMES,
    PREDICT_CLAIM,
    PredictRecipe,
    compare_predict_case,
    fit_predict_case,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import ComparisonProvenance, require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_MGCV_KEYS = {"mgcv", "lpmatrix", "response", "eta_train", "sp", "edf_total"}


def test_every_declared_quantity_is_independent_and_gates_parity() -> None:
    assert all(q.provenance is ComparisonProvenance.INDEPENDENT for q in PREDICT_CLAIM.quantities)
    require_parity_evidence(PREDICT_CLAIM.quantities, claim="predict.gam")


def test_the_polaris_producer_structurally_cannot_see_an_mgcv_output() -> None:
    """ADR-193's mechanical test, on the signature: the recipe type carries no
    key an ``mgcv`` output travels under."""
    assert not set(typing.get_type_hints(PredictRecipe)) & _MGCV_KEYS
    hints = typing.get_type_hints(fit_predict_case)
    assert hints["recipe"] is PredictRecipe


def _synthetic_recipe(name: str, seed: int = 3) -> PredictRecipe:
    rng = np.random.default_rng(seed)
    n = 80

    def cols(m: int) -> dict[str, list[float]]:
        c: dict[str, list[float]] = {
            "x": rng.uniform(0, 10, m).tolist(),
            "age": rng.uniform(45, 85, m).tolist(),
            "year": rng.uniform(2010, 2021, m).tolist(),
            "dur": rng.uniform(2, 22, m).tolist(),
            "z": rng.uniform(0, 5, m).tolist(),
            "w": rng.uniform(-2, 2, m).tolist(),
            "f": rng.integers(0, 3, m).tolist(),
            "A": rng.integers(0, 3, m).tolist(),
            "B": rng.integers(0, 2, m).tolist(),
            "off": rng.uniform(3.0, 5.0, m).tolist(),
        }
        return c

    return PredictRecipe(
        name=name,
        family="gaussian",
        link="identity",
        offset_column="off" if name == "poisson_offset" else None,
        n_levels={"f": 3, "A": 3, "B": 2},
        train=cols(n),
        y=rng.normal(size=n).tolist(),
        new_inrange=cols(7),
        new_outrange=cols(5),
        fit_polaris=False,
    )


@pytest.mark.parametrize("name", PREDICT_CASE_NAMES)
def test_every_cell_spec_builds_and_designs_have_the_new_row_counts(name: str) -> None:
    recipe = _synthetic_recipe(name)
    recipe["n_levels"] = {k: v for k, v in recipe["n_levels"].items() if k in _factor_names(name)}
    got = fit_predict_case(recipe)
    assert got.design_inrange.shape[0] == 7
    assert got.design_outrange.shape[0] == 5
    assert got.design_inrange.shape[1] == got.design_outrange.shape[1]


def _factor_names(name: str) -> set[str]:
    return {
        "gaussian_cr_by_ti": set(),
        "gaussian_factor_by": {"f"},
        "gaussian_parametric": {"A", "B"},
        "quasipoisson_cr_re_ti": {"f"},
        "binomial_cr": set(),
        "poisson_offset": set(),
        "poisson_hgam": set(),
        "gaussian_select": set(),
        "gaussian_sz": {"f"},
    }[name]


def test_unknown_cell_is_refused() -> None:
    recipe = _synthetic_recipe("gaussian_cr_by_ti")
    recipe["name"] = "nope"
    with pytest.raises((PolarisValidationError, KeyError)):
        fit_predict_case(recipe)


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_probe_runs_and_the_lpmatrix_agrees_on_every_cell(tmp_path: Path) -> None:
    out = tmp_path / "gam_predict_probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_predict_probe.R"), str(out)],
        check=True,
        capture_output=True,
        env={"OPENBLAS_NUM_THREADS": "1", "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )
    payload = json.loads(out.read_text())
    assert [c["name"] for c in payload["cells"]] == list(PREDICT_CASE_NAMES)
    for cell in payload["cells"]:
        # Independence: stripping every mgcv output leaves a bit-identical Polaris side.
        stripped = {k: v for k, v in cell.items() if k != "mgcv"}
        a = fit_predict_case(copy.deepcopy(stripped))  # type: ignore[arg-type]
        comparison = compare_predict_case(a, cell)
        assert comparison.max_abs_lpmatrix_diff_inrange < 1e-9, cell["name"]
        assert comparison.max_abs_lpmatrix_diff_outrange < 1e-9, cell["name"]
        if cell["name"] == "gaussian_factor_by":
            # Slice 9 (ADR-255): the unidentified coefficient is pivoted out, so Vp and the
            # Vp-based se are returned and gated; Vc is refused (its V'' term is not
            # pivot-invariant), which is a stated limitation and not a miss.
            assert comparison.vcov_refusal is None
            assert comparison.unconditional_refusal is not None
            assert comparison.se_agrees
        elif cell["fit_polaris"]:
            assert comparison.vcov_refusal is None, cell["name"]
            assert comparison.se_agrees, cell["name"]
        assert comparison.agrees, cell["name"]
