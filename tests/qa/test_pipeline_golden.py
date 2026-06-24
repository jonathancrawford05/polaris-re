"""Golden output regression tests — config-driven CLI pipeline path.

Every ``data/qa/golden_config_*.json`` is enumerated, priced through the same
parser/pipeline the CLI uses, and compared against a committed baseline in
``golden_outputs/``. Configs whose mortality source needs the SOA tables are
skipped when those tables are absent (CI-safe). The ``flat`` config always runs.

This replaces the previous hand-built ``flat``/``yrt`` baselines (which left the
``coins`` and ``policy_cession`` configs covered by CLI smoke tests only). The
shared machinery lives in ``golden_runner`` so the generator script and these
tests can never disagree on how a baseline is computed.
"""

import pytest

from .golden_runner import (
    compare_golden,
    discover_golden_cases,
    has_soa_tables,
    load_golden,
    load_inputs,
    run_pricing,
    save_golden,
)

# Enumerated once at collection — one parametrized regression case per config.
_GOLDEN_CASES = discover_golden_cases()


class TestGoldenRegression:
    """Per-config byte-level pipeline regression against committed baselines."""

    @pytest.mark.parametrize("case", _GOLDEN_CASES, ids=lambda c: c.name)
    def test_golden_regression(self, case):
        """Pricing for each golden config must match its committed baseline."""
        if case.needs_soa and not has_soa_tables():
            pytest.skip(f"{case.name}: SOA VBT 2015 tables required")

        actual = run_pricing(load_inputs(case))
        expected = load_golden(case.name)

        if expected is None:
            save_golden(actual, case.name)
            pytest.skip(
                f"Golden baseline not found — generated at {case.baseline_path}. "
                f"Commit this file and re-run."
            )

        failures = compare_golden(actual, expected, case.name)
        if failures:
            # Overwrite a *_actual sibling so the diff is visible in git.
            save_golden(actual, f"{case.name}_actual")
            pytest.fail(
                f"Golden output regression ({len(failures)} failures):\n"
                + "\n".join(f"  * {f}" for f in failures)
            )


class TestGoldenBaselineCoverage:
    """Drift guard: every committed config must have a committed baseline."""

    def test_every_config_has_committed_baseline(self):
        """A new golden_config_* without a committed baseline fails loudly here.

        Runs regardless of SOA tables — it is a pure file-existence check, so a
        config dropped into data/qa/ can never silently regress to smoke-only
        coverage (PR #103 review P2). Fix: run ``generate_golden.py`` and commit
        the new ``golden_outputs/<name>.json``.
        """
        assert _GOLDEN_CASES, "No golden_config_*.json discovered under data/qa/"
        missing = [c.name for c in _GOLDEN_CASES if not c.baseline_path.exists()]
        assert not missing, (
            f"golden_config_* without a committed baseline: {missing}. "
            f"Run `uv run python tests/qa/generate_golden.py` and commit "
            f"tests/qa/golden_outputs/."
        )

    def test_discovers_all_known_configs(self):
        """Sanity: the four shipped configs are all discovered."""
        names = {c.name for c in _GOLDEN_CASES}
        assert {
            "golden_flat",
            "golden_yrt",
            "golden_coins",
            "golden_policy_cession",
        } <= names, names


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
