"""Preview slice P5 (ADR-254): the user guide, its notebook, its data and the report script.

These are executable-documentation and own-criterion tests. None of them is parity
evidence: the comparison with ``mgcv`` is ``scripts/gam_parity_report.py`` in CI.
"""

import importlib.util
import inspect
import re
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.gam_predict_conformance import _SE_REL_TOLERANCE
from polaris_re.analytics.gam_select_free_sp_conformance import (
    _AGREEMENT_TOLERANCE_EDF,
    _AGREEMENT_TOLERANCE_ETA,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import evidence_markdown
from polaris_re.gam import GUIDE_FAMILY, GUIDE_FORMULA, gam, load_guide_example
from polaris_re.gam.guide_conformance import (
    GUIDE_CLAIM,
    compare_guide_predict,
    predict_guide_example,
)

ROOT = Path(__file__).resolve().parents[2]
GUIDE = (ROOT / "docs" / "GAM_USER_GUIDE.md").read_text()
WORKFLOW = (ROOT / ".github" / "workflows" / "mgcv-conformance.yml").read_text()


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def example_fit():
    train, new = load_guide_example()
    return gam(GUIDE_FORMULA, train, GUIDE_FAMILY), train, new


def test_the_guide_code_blocks_run_in_order() -> None:
    blocks = re.findall(r"```python\n(.*?)```", GUIDE, flags=re.S)
    assert len(blocks) >= 4
    scope: dict[str, object] = {}
    for block in blocks:
        exec(compile(block, "<GAM_USER_GUIDE.md>", "exec"), scope)


def test_the_notebook_code_cells_run() -> None:
    builder = _load_script("build_gam_preview_notebook")
    scope: dict[str, object] = {}
    for source in builder.code_cells():
        exec(compile(source, "<notebook>", "exec"), scope)
    assert (ROOT / "notebooks" / "gam_parity_preview.ipynb").exists()


def test_the_example_data_are_the_documented_shape() -> None:
    train, new = load_guide_example()
    assert train.shape == (800, 5) and new.shape == (60, 4)
    assert train.columns == ["deaths", "age", "duration", "sex", "log_exposure"]
    assert new.columns == ["age", "duration", "sex", "log_exposure"]
    assert float((train["deaths"] > 0).mean()) > 0.9  # counts carry signal (cf. ADR-253)
    # held-out rows sit strictly inside the training range: no extrapolation in the example
    assert new["age"].min() > train["age"].min() and new["age"].max() < train["age"].max()
    assert set(new["sex"].unique()) <= set(train["sex"].unique())


def test_the_r_probe_fits_the_same_formula_string_as_the_guide() -> None:
    """The R probe has the formula as text; a drift between it and ``GUIDE_FORMULA`` would
    make the report's guide row compare two different models."""
    text = (ROOT / "scripts" / "gam_formula_probe.R").read_text()
    block = text.split('cell("guide_example",')[1].split('"quasipoisson"')[0]
    literals = re.findall(r'"((?:[^"\\]|\\.)*)"', block)
    assert "".join(literals) == GUIDE_FORMULA


def test_the_guide_states_the_tolerances_and_digest_the_report_uses() -> None:
    assert f"`{_AGREEMENT_TOLERANCE_ETA:g}`" in GUIDE.replace("`2e-2`", "`0.02`")
    assert _AGREEMENT_TOLERANCE_ETA == 2e-2 and _SE_REL_TOLERANCE == 2e-2
    assert _AGREEMENT_TOLERANCE_EDF == 1.0
    digest = re.search(r"ORACLE_IMAGE: \S+@(sha256:[0-9a-f]{64})", WORKFLOW)
    assert digest is not None
    assert digest.group(1) in GUIDE, "the guide must name the digest the workflow pins"
    assert "R 4.6.1 / `mgcv` 1.9.4" in GUIDE


def test_the_guide_says_preview_and_never_claims_general_compatibility() -> None:
    assert "**Preview.**" in GUIDE
    for line in GUIDE.splitlines():
        if "mgcv-compatible" in line.lower() or "mgcv compatible" in line.lower():
            assert "not" in line.lower(), f"unqualified compatibility claim: {line!r}"


# Every construct the guide's §6 lists as refused, with a call that must refuse it.
_REFUSALS: dict[str, tuple[str, dict[str, object]]] = {
    "a bare `s(x)`": ("deaths ~ s(age)", {}),
    'bs="tp"': ('deaths ~ s(age, bs="tp")', {}),
    "`te()`": ("deaths ~ te(age, duration)", {}),
    "`scale=`": ('deaths ~ s(age, bs="cr")', {"scale": 1.0}),
    "`log(x)`": ("deaths ~ log(age)", {}),
    "`select=TRUE` with a factor-`by` smooth AND any other smooth": (
        'deaths ~ sex + s(age, bs="cr") + s(age, by=sex, bs="cr")',
        {"select": True},
    ),
}


@pytest.mark.parametrize("construct", sorted(_REFUSALS))
def test_every_refusal_in_the_guide_table_is_listed_and_refused(construct: str) -> None:
    assert construct in GUIDE, f"{construct!r} is not in the guide's refusal table"
    train, _ = load_guide_example()
    formula, kwargs = _REFUSALS[construct]
    with pytest.raises(PolarisValidationError):
        gam(formula, train, "quasipoisson", **kwargs)  # type: ignore[arg-type]


def test_the_supported_equivalent_of_a_refused_form_is_accepted() -> None:
    """Maintainer 2026-10-07: a bare s(x) stays refused only while the same model can be fitted
    with an explicit basis. The guide's advice for the rank-deficient form is checked too."""
    train, _ = load_guide_example()
    fit = gam(
        'deaths ~ offset(log_exposure) + sex + s(age, by=sex, bs="cr", k=6)', train, "poisson"
    )
    assert fit.converged


def test_the_rank_deficient_form_is_in_the_supported_table_and_fitted_with_a_pivot() -> None:
    """Slice 9 moved ``s(x) + s(x, by=f)`` from the refusal table to the supported one."""
    assert "`s(x) + s(x, by=f)` (with or without `f`)" in GUIDE.split("## 6.")[0]
    train, _ = load_guide_example()
    fit = gam(
        'deaths ~ offset(log_exposure) + s(age, bs="cr", k=6) + s(age, by=sex, bs="cr", k=6)',
        train,
        "poisson",
    )
    assert fit.converged and len(fit.pivoted_columns) == 1


def test_predict_with_se_is_internally_consistent(example_fit) -> None:
    """Own-criterion (not parity): se.fit on the response scale is the delta method
    ``mu * se_link`` for a log link, and Vc >= Vp row-wise."""
    fit, _, new = example_fit
    link, se = fit.predict(new, "link", se_fit=True)
    mu, se_mu = fit.predict(new, "response", se_fit=True)
    _, se_c = fit.predict(new, "link", se_fit=True, unconditional=True)
    np.testing.assert_allclose(mu, np.exp(link), rtol=1e-12)
    np.testing.assert_allclose(se_mu, mu * se, rtol=1e-10)
    assert np.all(se_c >= se * (1 - 1e-12))


def test_the_summary_carries_what_the_guide_says_it_does(example_fit) -> None:
    fit, train, _ = example_fit
    text = str(fit.summary())
    for needle in ("edf", "log10(sp)", "scale est.", "REML score", "Deviance explained"):
        assert needle in text
    assert f"n = {len(train)}" in text
    assert "No p-values" in text


def test_the_guide_producer_takes_no_mgcv_output() -> None:
    """The ADR-193 mechanical test, on the signature."""
    assert list(inspect.signature(predict_guide_example).parameters) == ["fit", "newdata"]
    keys = set(
        inspect.get_annotations(
            inspect.signature(predict_guide_example).parameters["newdata"].annotation
        )
    )
    assert keys == {"age", "duration", "sex", "log_exposure"}


def test_the_projection_inside_the_producer_drops_extra_keys(example_fit) -> None:
    """A caller may hand over the whole probe block; the mgcv keys must not be read."""
    fit, _, new = example_fit
    cols = {c: new[c].to_list() for c in new.columns}
    clean = predict_guide_example(fit, cols)  # type: ignore[arg-type]
    polluted = predict_guide_example(fit, {**cols, "link": [0.0] * 60})  # type: ignore[arg-type]
    np.testing.assert_array_equal(clean.link, polluted.link)


def test_compare_guide_predict_arithmetic_on_a_perturbed_reference(example_fit) -> None:
    """HARNESS test, not parity: the reference here is Polaris's own output, perturbed by a
    known amount, so the comparison's arithmetic and its gates are exercised."""
    fit, _, new = example_fit
    cols = {c: new[c].to_list() for c in new.columns}
    mine = predict_guide_example(fit, cols)  # type: ignore[arg-type]
    exact = {
        "link": mine.link.tolist(),
        "link_se": mine.link_se.tolist(),
        "link_se_unconditional": mine.link_se_unconditional.tolist(),
        "response": mine.response.tolist(),
        "response_se": mine.response_se.tolist(),
    }
    same = compare_guide_predict(mine, exact)
    assert same.agrees and same.max_abs_link_diff == 0.0
    off = dict(exact, link_se=(mine.link_se * 1.05).tolist())
    result = compare_guide_predict(mine, off)
    assert not result.agrees
    assert result.max_rel_link_se == pytest.approx(0.05 / 1.05, rel=1e-9)
    shifted = dict(exact, link=(mine.link + 0.05).tolist())
    assert not compare_guide_predict(mine, shifted).agrees


def test_the_guide_claim_is_all_independent_and_its_headline_is_derived() -> None:
    assert GUIDE_CLAIM.is_parity_claim
    assert evidence_markdown(GUIDE_CLAIM).startswith("**Parity comparison**")


def test_the_report_refuses_to_run_without_a_digest(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "gam_parity_report.py"
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, str(script), str(tmp_path), str(tmp_path / "r.md")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 2
    assert "--digest" in done.stderr


def test_a_report_with_no_probes_says_not_measured_and_incomplete(tmp_path: Path) -> None:
    report = _load_script("gam_parity_report")
    header = ["# GAM parity report — PREVIEW", "", "> **TIER 1 — LOCAL**"]
    text, complete = report.build(tmp_path, header)
    assert not complete
    assert text.count("NOT MEASURED") >= 5
    assert "NOT ALL SECTIONS AGREE OR WERE MEASURED" in text
    assert "ALL MEASURED SECTIONS AGREE" not in text.replace("NOT ALL", "")


def test_the_report_step_is_in_the_workflow_and_stamps_run_and_digest() -> None:
    marker = "uv run python scripts/gam_parity_report.py"
    assert marker in WORKFLOW, "the workflow must run scripts/gam_parity_report.py"
    block = WORKFLOW[WORKFLOW.index(marker) :][:400]
    for flag in ("--run-id", "--commit", "--digest"):
        assert flag in block


def test_the_example_data_loads_with_polars_only() -> None:
    train, _ = load_guide_example()
    assert isinstance(train, pl.DataFrame)
