"""``docs/CONTINUATION_mgcv_parity_engine.md``, slice 5's remaining scope — the
first multi-term mgcv-native model's Stage-B conformance.

The genuine parity check: :func:`fit_multiterm_case` (an independent Python
assembly + fit) against ``scripts/gam_multiterm_probe.R``'s own native
``mgcv::gam()`` fit of the identical three-term formula, on the SAME shared
recipe at a fixed ``sp`` for every block. Gated on R being present, same
discipline as ``test_gam_family_conformance.py``.
"""

import json
import subprocess
from pathlib import Path

import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_multiterm_conformance import (
    MULTITERM_CLAIM,
    RMultiTermPayload,
    RMultiTermRecipe,
    compare_multiterm_case,
    fit_multiterm_case,
)
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_multiterm_claim_is_independent_on_every_declared_quantity() -> None:
    """ADR-193's gate: a harness result must not be able to satisfy this."""
    require_parity_evidence(MULTITERM_CLAIM.quantities, claim=MULTITERM_CLAIM.claim)
    assert MULTITERM_CLAIM.is_parity_claim


def test_fit_multiterm_case_signature_takes_no_r_fit_output() -> None:
    """ADR-193's mechanical test, applied structurally at the type, same
    discipline PR #202 review [P1] established for
    :func:`~polaris_re.analytics.gam_family_conformance.fit_family_case`:
    ``r_case`` is annotated :class:`RMultiTermRecipe`, which has no
    ``eta``/``coef`` key at all, so a body that indexed one would be a `mypy`
    error rather than merely a convention nobody enforces."""
    import inspect
    import typing

    params = set(inspect.signature(fit_multiterm_case).parameters)
    assert params == {"r_case"}

    hints = typing.get_type_hints(fit_multiterm_case)
    assert hints["r_case"] is RMultiTermRecipe

    recipe_keys = set(RMultiTermRecipe.__annotations__)
    payload_keys = set(RMultiTermPayload.__annotations__)
    fit_only_keys = {"eta", "coef", "converged"}
    assert recipe_keys.isdisjoint(fit_only_keys)
    assert fit_only_keys <= payload_keys
    assert recipe_keys < payload_keys


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_r_probe_runs_end_to_end_and_agrees(tmp_path) -> None:  # pragma: no cover
    """The real conformance run, when R happens to be present.

    A disagreement here is a real result (PLAN Anchor 9: the multi-term
    assembly — column order, per-block penalty padding, or one of the three
    basis producers themselves — differs from mgcv's for this combination),
    not a test bug to paper over.
    """
    out_path = tmp_path / "gam_multiterm_probe.json"
    done = subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_multiterm_probe.R"), str(out_path)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr

    payload = json.loads(out_path.read_text())
    fit, _design = fit_multiterm_case(payload)
    comparison = compare_multiterm_case(fit, payload)
    assert comparison["agrees"], comparison
