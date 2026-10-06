"""Outer-solver slice 4 (ADR-245): the gauntlet's plumbing — ``outer`` reaches
every fit helper, one Newton start per scale (no seeded second start), failures
are reported rather than dropped, and the parity gate refuses a harness claim."""

import inspect

import pytest

from polaris_re.analytics import gam_quasipoisson_fixed_scale_conformance as fixed_scale
from polaris_re.analytics.gam_by_factor_conformance import fit_by_factor_free_sp_case
from polaris_re.analytics.gam_cr_re_ti_conformance import fit_cr_re_ti_free_sp_case
from polaris_re.analytics.gam_gaussian_conformance import fit_gaussian_free_sp_case
from polaris_re.analytics.gam_newton_gauntlet_conformance import (
    REQUIRED_CASE_PREFIXES,
    GauntletReading,
    gate_failures,
    gauntlet_claims,
    require_gauntlet_parity_evidence,
    run_gauntlet,
)
from polaris_re.analytics.gam_parametric_conformance import fit_parametric_free_sp_case
from polaris_re.analytics.gam_production_mi_conformance import (
    PRODUCTION_MI_NEWTON_CLAIM,
    fit_production_mi_case,
)
from polaris_re.analytics.gam_quasipoisson_conformance import fit_quasipoisson_free_sp_case
from polaris_re.analytics.gam_select_free_sp_conformance import fit_select_free_sp_case
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)


@pytest.mark.parametrize(
    "fit",
    [
        fit_gaussian_free_sp_case,
        fit_by_factor_free_sp_case,
        fit_parametric_free_sp_case,
        fit_cr_re_ti_free_sp_case,
        fit_quasipoisson_free_sp_case,
        fixed_scale.fit_quasipoisson_fixed_scale_case,
        fit_select_free_sp_case,
    ],
)
def test_every_gauntlet_fit_helper_accepts_outer_and_defaults_to_lbfgsb(fit: object) -> None:
    param = inspect.signature(fit).parameters["outer"]  # type: ignore[arg-type]
    assert param.default == "lbfgsb"


def test_fixed_scale_newton_is_one_start_per_scale(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gauntlet's rule is ONE start: no gamma=1 seed, no best-of-two."""
    calls: list[dict[str, object]] = []

    def spy(*args: object, **kwargs: object) -> str:
        calls.append(dict(kwargs))
        return "fit"

    monkeypatch.setattr(fixed_scale, "_model_and_data", lambda r: ("m", {}, None))
    monkeypatch.setattr(fixed_scale, "fit_polaris_gam", spy)
    out = fixed_scale.fit_quasipoisson_fixed_scale_case(
        {"scales": [2.0, 6.0]},  # type: ignore[typeddict-item]
        outer="newton",
    )
    assert out == ["fit", "fit"]
    assert [c["gamma"] for c in calls] == [2.0, 6.0]
    assert all(c["outer"] == "newton" and "x0" not in c and "multistart" not in c for c in calls)


def test_a_case_that_raises_is_reported_not_dropped() -> None:
    readings = run_gauntlet({})  # every payload lookup fails
    assert len(readings) == 9  # six free-scale cells + fixed scale + select + HGAM
    assert all(r.error is not None and not r.agrees for r in readings)


def _claim(provenance: ComparisonProvenance) -> VerificationClaim:
    return VerificationClaim(
        claim="x",
        quantities=(
            ComparedQuantity(
                quantity="eta",
                left_producer="polaris",
                right_producer="mgcv"
                if provenance is ComparisonProvenance.INDEPENDENT
                else "polaris",
                provenance=provenance,
            ),
        ),
    )


def _reading(claim: VerificationClaim) -> GauntletReading:
    return GauntletReading("c", 0.0, 0.0, 1, False, True, True, claim)


def test_gate_passes_on_independent_and_refuses_a_harness_claim() -> None:
    require_gauntlet_parity_evidence([_reading(_claim(ComparisonProvenance.INDEPENDENT))])
    with pytest.raises(PolarisValidationError):
        require_gauntlet_parity_evidence([_reading(_claim(ComparisonProvenance.TRANSPORT))])


def test_claims_are_deduplicated_by_text() -> None:
    c = _claim(ComparisonProvenance.INDEPENDENT)
    assert len(gauntlet_claims([_reading(c), _reading(c)])) == 1


def _row(case: str, *, agrees: bool = True, converged: bool = True) -> GauntletReading:
    return GauntletReading(
        case=case,
        max_abs_eta_diff=0.0,
        edf_total_diff=0.0,
        n_function_evals=1,
        at_bound=False,
        converged=converged,
        agrees=agrees,
        evidence=None,
    )


def test_gate_passes_only_on_both_fixed_scale_rows_agreeing() -> None:
    ok = [_row("quasipoisson fixed scale=2"), _row("quasipoisson fixed scale=6"), _row("other")]
    assert gate_failures(ok) == []


@pytest.mark.parametrize(
    "rows",
    [
        [_row("quasipoisson fixed scale=2")],  # a dropped scale never passes by omission
        [],
        [_row("quasipoisson fixed scale=2"), _row("quasipoisson fixed scale=6", agrees=False)],
        [_row("quasipoisson fixed scale=2"), _row("quasipoisson fixed scale=6", converged=False)],
    ],
)
def test_gate_fails_on_missing_disagreeing_or_unconverged_rows(rows: list[GauntletReading]) -> None:
    assert gate_failures(rows)


def test_gate_surfaces_an_error_row_as_a_failure() -> None:
    errored = run_gauntlet({})
    assert any("error=" in f for f in gate_failures(errored))


def test_gate_does_not_block_on_other_cases() -> None:
    rows = [
        _row("quasipoisson fixed scale=2"),
        _row("quasipoisson fixed scale=6"),
        _row("select=TRUE N=7", agrees=False),
    ]
    assert gate_failures(rows) == []
    assert REQUIRED_CASE_PREFIXES == ("quasipoisson fixed scale",)


def test_hgam_producer_signature_takes_the_recipe_only_and_defaults_to_lbfgsb() -> None:
    params = inspect.signature(fit_production_mi_case).parameters
    assert params["outer"].default == "lbfgsb"
    assert not {"eta", "coef", "sp", "edf", "r_fit", "anova", "te"} & set(params)


def test_hgam_newton_claim_declares_only_the_two_columns_it_compares() -> None:
    assert [q.quantity.split(" ")[0] for q in PRODUCTION_MI_NEWTON_CLAIM.quantities] == [
        "eta",
        "edf_total",
    ]
    assert all(
        q.provenance is ComparisonProvenance.INDEPENDENT
        for q in PRODUCTION_MI_NEWTON_CLAIM.quantities
    )
    assert "multistart=True" not in PRODUCTION_MI_NEWTON_CLAIM.claim


# --- the script's --gate exit path (PR #255 review; ADR-246) ----------------


def _load_gauntlet_script():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "gam_newton_gauntlet.py"
    spec = importlib.util.spec_from_file_location("gam_newton_gauntlet_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _patched_script(monkeypatch: pytest.MonkeyPatch, rows: list[GauntletReading]) -> object:
    script = _load_gauntlet_script()
    monkeypatch.setattr(script, "payloads_from_probe_dir", lambda _read: {})
    monkeypatch.setattr(script, "run_gauntlet", lambda _payloads: rows)
    monkeypatch.setattr(script, "require_gauntlet_parity_evidence", lambda _rows: None)
    monkeypatch.setattr(script, "gauntlet_claims", lambda _rows: [])
    return script


def test_gate_flag_exits_one_when_a_fixed_scale_row_disagrees(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    rows = [
        _row("quasipoisson fixed scale=2"),
        _row("quasipoisson fixed scale=6", agrees=False),
    ]
    script = _patched_script(monkeypatch, rows)
    with pytest.raises(SystemExit) as excinfo:
        script.main(tmp_path, None, gate=True)  # type: ignore[attr-defined]
    assert excinfo.value.code == 1


def test_gate_flag_returns_normally_when_both_fixed_scale_rows_agree(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    rows = [_row("quasipoisson fixed scale=2"), _row("quasipoisson fixed scale=6")]
    script = _patched_script(monkeypatch, rows)
    script.main(tmp_path, None, gate=True)  # type: ignore[attr-defined]


def test_without_the_gate_flag_a_disagreement_is_reported_not_fatal(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    rows = [
        _row("quasipoisson fixed scale=2", agrees=False),
        _row("quasipoisson fixed scale=6"),
    ]
    script = _patched_script(monkeypatch, rows)
    script.main(tmp_path, None, gate=False)  # type: ignore[attr-defined]


# --- case 5, the thread axis (ADR-247) --------------------------------------


def test_thread_axis_covers_every_newton_case_and_enters_each_thread_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import contextlib
    from types import SimpleNamespace

    import numpy as np

    from polaris_re.analytics import gam_newton_gauntlet_conformance as g

    entered: list[int] = []

    @contextlib.contextmanager
    def limit(n: int):
        entered.append(n)
        yield

    calls = {"n": 0}

    def fake_fits(_label, _payloads):
        calls["n"] += 1
        bump = 1e-9 * (calls["n"] % 3)  # differs across calls, so the diff is real
        return [
            SimpleNamespace(
                eta=np.array([1.0 + bump, 2.0]),
                log_lambda=np.array([0.5, 1.0 + bump]),
                edf_total=3.0 + bump,
                converged=True,
                n_function_evals=7,
            )
        ]

    monkeypatch.setattr(g, "_newton_fits_for_case", fake_fits)
    rows = g.run_thread_axis({}, limit, threads=(1, 2, 4, 1))
    assert [r.case for r in rows] == list(g.THREAD_AXIS_CASES)
    assert entered[:4] == [1, 2, 4, 1]
    assert all(r.error is None and r.all_converged for r in rows)
    assert all(r.n_function_evals == (7, 7, 7, 7) for r in rows)
    assert any(r.max_abs_eta_diff > 0.0 for r in rows)


def test_thread_axis_reports_a_raising_case_instead_of_dropping_it() -> None:
    import contextlib

    from polaris_re.analytics.gam_newton_gauntlet_conformance import (
        THREAD_AXIS_CASES,
        run_thread_axis,
    )

    rows = run_thread_axis({}, lambda _n: contextlib.nullcontext())  # no payloads: KeyError
    assert len(rows) == len(THREAD_AXIS_CASES)
    assert all(r.error for r in rows)


# --- ADR-248: log10(sp) is reported (never gated) per block -----------------


def test_reading_carries_log10_sp_from_a_typeddict_or_a_dataclass_comparison() -> None:
    from types import SimpleNamespace

    import numpy as np

    from polaris_re.analytics import gam_newton_gauntlet_conformance as g

    claim = _claim(ComparisonProvenance.INDEPENDENT)
    fit = SimpleNamespace(n_function_evals=3, log_lambda=np.array([1.0, 2.0]))
    common = {
        "max_abs_eta_diff": 1e-5,
        "edf_total_diff": 0.0,
        "at_bound": False,
        "converged": True,
        "agrees": True,
        "evidence": claim,
    }
    as_dict = g._reading("c", fit, {**common, "max_abs_log10_sp_diff": 0.25})  # type: ignore[arg-type]
    as_obj = g._reading("c", fit, SimpleNamespace(**common, max_abs_log10_sp_diff=0.5))  # type: ignore[arg-type]
    absent = g._reading("c", fit, SimpleNamespace(**common))  # type: ignore[arg-type]
    assert as_dict.max_abs_log10_sp_diff == 0.25
    assert as_obj.max_abs_log10_sp_diff == 0.5
    assert absent.max_abs_log10_sp_diff is None  # not declared -> not reported


def test_per_block_sp_diff_is_polaris_minus_mgcv_and_none_when_unusable() -> None:
    from types import SimpleNamespace

    import numpy as np

    from polaris_re.analytics import gam_newton_gauntlet_conformance as g

    fit = SimpleNamespace(log_lambda=np.array([3.0, 1.0]))
    diff = g._per_block_sp_diff(fit, {"sp": [100.0, 100.0]})  # type: ignore[arg-type]
    assert diff is not None
    np.testing.assert_allclose(diff, (1.0, -1.0))
    other_key = g._per_block_sp_diff(fit, {"mgcv_sp": [1000.0, 10.0]})  # type: ignore[arg-type]
    assert other_key is not None
    np.testing.assert_allclose(other_key, (0.0, 0.0))
    assert g._per_block_sp_diff(fit, {"sp": [1.0]}) is None  # type: ignore[arg-type]
    assert g._per_block_sp_diff(fit, {}) is None  # type: ignore[arg-type]


def test_script_reports_the_select_true_per_block_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    from dataclasses import replace

    row = replace(
        _row("select=TRUE N=7 (cr+by+ti, 7 blocks)"),
        max_abs_log10_sp_diff=0.3,
        log10_sp_diff_per_block=(0.3, -0.01),
    )
    script = _patched_script(monkeypatch, [row, _row("gaussian L1 (cr+by+ti)")])
    script.main(tmp_path, None, gate=False)  # type: ignore[attr-defined]
    out = capsys.readouterr().out
    assert "b0: +0.300, b1: -0.010" in out
    assert "| n/a |" in out  # a row whose comparison declares no log10(sp)
