"""``polaris_re.gam.formula_conformance`` — preview Slice P3 (ADR-251).

R-free: the provenance gate (ADR-193), the layering rule, the expected-refusal logic.
R-gated: the probe is run and read (tier 1 here — a regression check only; the
committed number is the tier-3 CI reading)."""

import json
import subprocess
import typing
from pathlib import Path

import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.core.verification import ComparisonProvenance, require_parity_evidence
from polaris_re.gam.formula_conformance import (
    EXPECTED_REFUSALS,
    FORMULA_CLAIM,
    FormulaCaseFit,
    FormulaPayload,
    FormulaRecipe,
    compare_formula_case,
    fit_formula_case,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_MGCV_KEYS = {"mgcv", "eta", "edf_total", "labels", "levels", "sp", "scale", "nsdf"}


def test_every_declared_quantity_is_independent_and_gates_parity() -> None:
    assert all(q.provenance is ComparisonProvenance.INDEPENDENT for q in FORMULA_CLAIM.quantities)
    require_parity_evidence(FORMULA_CLAIM.quantities, claim="formula front end")


def test_the_polaris_producer_structurally_cannot_see_an_mgcv_output() -> None:
    """ADR-193's mechanical test, on the signature."""
    assert not set(typing.get_type_hints(FormulaRecipe)) & _MGCV_KEYS
    assert typing.get_type_hints(fit_formula_case)["recipe"] is FormulaRecipe


def test_analytics_never_imports_the_gam_facade() -> None:
    """``polaris_re.gam`` depends on ``analytics``, never the reverse (PLAN P3)."""
    offenders = [
        str(p)
        for sub in ("analytics", "core")
        for p in (REPO_ROOT / "src" / "polaris_re" / sub).rglob("*.py")
        if "polaris_re.gam" in p.read_text()
    ]
    assert offenders == []


def _recipe(name: str, formula: str) -> FormulaRecipe:
    n = 60
    return FormulaRecipe(
        name=name,
        formula=formula,
        family="gaussian",
        select=False,
        weights_column=None,
        data={
            "x": [i * 10 / (n - 1) for i in range(n)],
            "f": ["a", "b", "c"] * (n // 3),
            "y": [((i * 7919) % 101) / 101 for i in range(n)],
        },
    )


def test_an_expected_refusal_agrees_only_when_polaris_refuses() -> None:
    name = next(iter(EXPECTED_REFUSALS))
    refused = fit_formula_case(_recipe(name, 'y ~ s(x, bs="cr", k=5) + s(x, by=f, bs="cr", k=5)'))
    assert refused.fit is None and refused.refusal is not None
    payload = typing.cast(FormulaPayload, {"mgcv": {}})
    assert compare_formula_case(refused, payload).agrees
    accepted = fit_formula_case(_recipe(name, 'y ~ f + s(x, by=f, bs="cr", k=5)'))
    assert accepted.fit is not None
    assert not compare_formula_case(accepted, payload).agrees


def test_an_unexpected_refusal_is_a_disagreement() -> None:
    case = FormulaCaseFit(name="binomial_cr", fit=None, refusal="boom")
    out = compare_formula_case(case, typing.cast(FormulaPayload, {"mgcv": {}}))
    assert out.refused and not out.expected_refusal and not out.agrees


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_probe_runs_and_every_cell_agrees_at_tier_one(tmp_path: Path) -> None:
    out = tmp_path / "probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_formula_probe.R"), str(out)],
        check=True,
        capture_output=True,
        env={"OPENBLAS_NUM_THREADS": "1", "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )
    payload = json.loads(out.read_text())
    assert {c["name"] for c in payload["cells"]} >= EXPECTED_REFUSALS
    for cell in payload["cells"]:
        result = compare_formula_case(fit_formula_case(cell), cell)
        assert result.agrees, (cell["name"], result)
