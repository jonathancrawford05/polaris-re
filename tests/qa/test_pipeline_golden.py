"""Golden output regression tests — CLI pipeline path.

Run the pricing engine on the golden inputs and compare against
committed baselines. When a baseline doesn't exist yet, generate it.
"""

import json

import pytest

from polaris_re.analytics.profit_test import ProfitTester
from polaris_re.core.pipeline import (
    build_pipeline,
    build_treaty,
    ceded_to_reinsurer_view,
    derive_yrt_rate,
    iter_cohorts,
)
from polaris_re.products.dispatch import get_product_engine

from .conftest import GOLDEN_OUTPUTS_DIR, requires_soa_tables

# Tolerance for golden output comparison ($ amount)
ABS_TOL_DOLLARS = 500.0
# Tolerance for percentage metrics
ABS_TOL_PCT = 0.005


def _run_pricing(inforce, inputs):
    """Run full pricing pipeline, return per-cohort results dict."""
    inf, assumptions, config = build_pipeline(inforce, inputs)
    cohorts = iter_cohorts(inf)
    results = {}

    for product_type, cohort_inforce in cohorts:
        gross = get_product_engine(
            inforce=cohort_inforce,
            assumptions=assumptions,
            config=config,
        ).project()

        face_amount = cohort_inforce.total_face_amount()
        yrt_rate = derive_yrt_rate(gross, face_amount, inputs.deal.yrt_loading)

        treaty = build_treaty(
            treaty_type=inputs.deal.treaty_type,
            cession_pct=inputs.deal.cession_pct,
            face_amount=face_amount,
            yrt_rate_per_1000=yrt_rate,
        )

        if treaty is not None:
            use_policy = inputs.deal.use_policy_cession
            inforce_arg = cohort_inforce if use_policy else None
            net, ceded = treaty.apply(gross, inforce=inforce_arg)
        else:
            net, ceded = gross, None

        cedant = ProfitTester(cashflows=net, hurdle_rate=inputs.deal.hurdle_rate).run()

        reinsurer = None
        if ceded is not None:
            reinsurer = ProfitTester(
                cashflows=ceded_to_reinsurer_view(ceded),
                hurdle_rate=inputs.deal.hurdle_rate,
            ).run()

        results[product_type.value] = {
            "n_policies": cohort_inforce.n_policies,
            "face_amount": face_amount,
            "cedant_pv_profits": cedant.pv_profits,
            "cedant_profit_margin": cedant.profit_margin,
            "cedant_irr": cedant.irr,
            "cedant_breakeven": cedant.breakeven_year,
            "reinsurer_pv_profits": (reinsurer.pv_profits if reinsurer else None),
            "reinsurer_profit_margin": (reinsurer.profit_margin if reinsurer else None),
            "gross_total_premiums": float(gross.gross_premiums.sum()),
            "gross_total_claims": float(gross.death_claims.sum()),
            "projection_months": gross.projection_months,
        }

    return results


def _save_golden(results: dict, name: str):
    """Save golden output as JSON baseline."""
    GOLDEN_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    path = GOLDEN_OUTPUTS_DIR / f"{name}.json"
    path.write_text(json.dumps(results, indent=2, default=str))
    return path


def _load_golden(name: str) -> dict | None:
    """Load golden output baseline, or None if not yet generated."""
    path = GOLDEN_OUTPUTS_DIR / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _compare_golden(actual: dict, expected: dict, label: str) -> list[str]:
    """Compare actual vs expected results, return list of discrepancies."""
    failures = []

    for cohort_key in expected:
        if cohort_key not in actual:
            failures.append(f"{label}/{cohort_key}: missing from actual")
            continue

        exp = expected[cohort_key]
        act = actual[cohort_key]

        for metric in [
            "cedant_pv_profits",
            "reinsurer_pv_profits",
            "gross_total_premiums",
            "gross_total_claims",
        ]:
            e_val = exp.get(metric)
            a_val = act.get(metric)
            if e_val is None and a_val is None:
                continue
            if e_val is None or a_val is None:
                failures.append(f"{label}/{cohort_key}/{metric}: expected={e_val}, actual={a_val}")
                continue
            if abs(float(a_val) - float(e_val)) > ABS_TOL_DOLLARS:
                failures.append(
                    f"{label}/{cohort_key}/{metric}: "
                    f"expected={float(e_val):,.2f}, "
                    f"actual={float(a_val):,.2f}, "
                    f"delta={float(a_val) - float(e_val):+,.2f}"
                )

        for metric in ["cedant_profit_margin", "reinsurer_profit_margin"]:
            e_val = exp.get(metric)
            a_val = act.get(metric)
            if e_val is None and a_val is None:
                continue
            if e_val is None or a_val is None:
                failures.append(f"{label}/{cohort_key}/{metric}: expected={e_val}, actual={a_val}")
                continue
            if abs(float(a_val) - float(e_val)) > ABS_TOL_PCT:
                failures.append(
                    f"{label}/{cohort_key}/{metric}: "
                    f"expected={float(e_val):.4%}, "
                    f"actual={float(a_val):.4%}"
                )

    return failures


class TestGoldenYRT:
    """Golden output tests for YRT treaty config."""

    GOLDEN_NAME = "golden_yrt"

    @requires_soa_tables
    def test_yrt_golden_regression(self, golden_inforce, golden_yrt_inputs):
        """YRT pricing must match golden baseline."""
        actual = _run_pricing(golden_inforce, golden_yrt_inputs)
        expected = _load_golden(self.GOLDEN_NAME)

        if expected is None:
            _save_golden(actual, self.GOLDEN_NAME)
            pytest.skip(
                f"Golden baseline not found — generated at "
                f"{GOLDEN_OUTPUTS_DIR / self.GOLDEN_NAME}.json. "
                f"Commit this file and re-run."
            )

        failures = _compare_golden(actual, expected, self.GOLDEN_NAME)
        if failures:
            # Overwrite with actual so the diff is visible in git
            _save_golden(actual, f"{self.GOLDEN_NAME}_actual")
            pytest.fail(
                f"Golden output regression ({len(failures)} failures):\n"
                + "\n".join(f"  * {f}" for f in failures)
            )


class TestGoldenFlat:
    """Golden output tests for flat mortality (CI-safe, no SOA tables)."""

    GOLDEN_NAME = "golden_flat"

    def test_flat_golden_regression(self, golden_inforce, golden_flat_inputs):
        """Flat-mortality pricing must match golden baseline."""
        actual = _run_pricing(golden_inforce, golden_flat_inputs)
        expected = _load_golden(self.GOLDEN_NAME)

        if expected is None:
            _save_golden(actual, self.GOLDEN_NAME)
            pytest.skip(
                f"Golden baseline not found — generated at "
                f"{GOLDEN_OUTPUTS_DIR / self.GOLDEN_NAME}.json. "
                f"Commit this file and re-run."
            )

        failures = _compare_golden(actual, expected, self.GOLDEN_NAME)
        if failures:
            _save_golden(actual, f"{self.GOLDEN_NAME}_actual")
            pytest.fail(
                f"Golden output regression ({len(failures)} failures):\n"
                + "\n".join(f"  * {f}" for f in failures)
            )


class TestGoldenSanity:
    """Sanity checks that don't depend on committed baselines."""

    def test_golden_csv_loads(self, golden_inforce):
        """Golden CSV loads without error and has expected policy count."""
        assert golden_inforce.n_policies == 12

    def test_golden_csv_has_both_product_types(self, golden_inforce):
        """Golden CSV contains both TERM and WHOLE_LIFE policies."""
        from polaris_re.core.policy import ProductType

        pts = golden_inforce.product_types
        assert ProductType.TERM in pts
        assert ProductType.WHOLE_LIFE in pts

    def test_golden_csv_has_policy_cession_overrides(self, golden_inforce):
        """At least 2 policies have reinsurance_cession_pct set."""
        overrides = [p for p in golden_inforce.policies if p.reinsurance_cession_pct is not None]
        assert len(overrides) >= 2

    def test_golden_csv_has_new_issue_policies(self, golden_inforce):
        """At least 1 policy with duration_inforce == 0."""
        new_issues = [p for p in golden_inforce.policies if p.duration_inforce == 0]
        assert len(new_issues) >= 1

    def test_cohort_partitioning(self, golden_inforce):
        """iter_cohorts splits golden block into exactly 2 cohorts."""
        from polaris_re.core.pipeline import iter_cohorts

        cohorts = iter_cohorts(golden_inforce)
        assert len(cohorts) == 2
        total = sum(sub.n_policies for _, sub in cohorts)
        assert total == 12
