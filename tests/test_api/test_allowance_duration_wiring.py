"""API wiring for block-aware expense-allowance duration mapping — Slice 2.

Slice 1 (ADR-166) let ``BaseTreaty.apply`` map a sliding-scale ``ExpenseAllowance``
to each policy's actual duration whenever an ``InforceBlock`` is supplied,
independent of the cession flag. Slice 2 rewires ``/api/v1/price`` to pass
``inforce`` to ``treaty.apply`` **always** (previously only on the tabular-YRT
path), so the high first-year allowance rate is charged only on business
genuinely in policy year one.

``PolicyInput`` carries no per-policy cession override (the API always builds
``Policy`` with ``reinsurance_cession_pct=None``), so passing ``inforce`` is
cession-neutral for existing responses — the existing byte-identical tests in
``test_expense_allowance_api.py`` still hold. What changes is that a
*mid-duration* block now charges the renewal (not new-business) allowance basis.
"""

from fastapi.testclient import TestClient

from polaris_re.api.main import app

client = TestClient(app)

# High first-year / low renewal allowance so the duration basis dominates the
# reinsurer→cedant transfer.
_ALLOWANCE = {"first_year_pct": 1.0, "renewal_pct": 0.10}


def _policy(*, issue_year: int, attained_age: int, months_in_force: int) -> dict:
    return {
        "policy_id": "DUR001",
        "issue_age": 45,
        "attained_age": attained_age,
        "sex": "M",
        "smoker": False,
        "underwriting_class": "STANDARD",
        "face_amount": 1_000_000.0,
        "annual_premium": 20_000.0,
        "policy_term": 30,
        "duration_inforce": months_in_force,
        "issue_date": f"{issue_year}-01-01",
        "valuation_date": "2026-01-01",
    }


def _base(policy: dict, **overrides) -> dict:
    payload = {
        "policies": [policy],
        "treaty_type": "Coinsurance",
        "cession_pct": 0.90,
        "projection_horizon_years": 10,
        "discount_rate": 0.06,
        "hurdle_rate": 0.10,
        "flat_qx": 0.003,  # age-independent ⇒ isolates the allowance-rate schedule
    }
    payload.update(overrides)
    return payload


def _allowance_transfer(policy: dict) -> float:
    """Undiscounted reinsurer→cedant allowance transfer for a policy, measured
    as the drop in the reinsurer's undiscounted profit when the allowance is
    added. Negative = reinsurer pays out."""
    base = client.post("/api/v1/price", json=_base(policy)).json()
    withal = client.post("/api/v1/price", json=_base(policy, expense_allowance=_ALLOWANCE)).json()
    return (
        withal["reinsurer_total_undiscounted_profit"] - base["reinsurer_total_undiscounted_profit"]
    )


def test_mid_duration_block_charges_renewal_not_first_year_basis() -> None:
    """A 10-year in-force block must be charged a SMALLER allowance than a
    matched new-business block, because the high first-year rate applies only to
    genuine policy-year-one business. Before Slice 2 both blocks got the
    new-business basis (identical transfer) — this pins the fix."""
    new_business = _policy(issue_year=2026, attained_age=45, months_in_force=0)
    mid_duration = _policy(issue_year=2016, attained_age=55, months_in_force=120)

    d_newbiz = _allowance_transfer(new_business)
    d_mid = _allowance_transfer(mid_duration)

    # Both pay an allowance out (negative), but the mid-duration block pays
    # materially less — no first-year rate on year-one business it is past.
    assert d_newbiz < 0.0
    assert d_mid < 0.0
    assert d_mid > d_newbiz  # smaller magnitude ⇒ closer to zero
    # The gap is the whole point: the first-year premium at 1.0 vs 0.10 dwarfs
    # any second-order difference, so require it to be clearly non-trivial.
    assert (d_mid - d_newbiz) > 0.01 * abs(d_newbiz)
