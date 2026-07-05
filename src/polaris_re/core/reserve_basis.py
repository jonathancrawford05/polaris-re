"""
ReserveBasis — the statutory/accounting basis used to value policy reserves.

A reinsurer pricing an inforce block must be able to reproduce the *cedant's*
reserve, not just a single net-premium reserve, because the reserve drives the
Net Amount at Risk (YRT), the proportional reserve transfer (coinsurance), and
the profit signature. Different jurisdictions and accounting regimes prescribe
different reserve methods:

- ``NET_PREMIUM`` — the classic net level premium reserve (the engine's
  historical behaviour and the default). Terminal condition ``V_T = 0`` for
  term, prospective terminal estimate for whole life.
- ``CRVM`` — Commissioners Reserve Valuation Method (US statutory). A modified
  reserve that grades in a first-year expense allowance, producing a lower
  first-year reserve than the pure net premium method.
- ``VM20`` — VM-20 simplified principle-based reserve (the deterministic
  reserve / net-premium-reserve floor of PBR for US life business).
- ``GAAP`` — US GAAP (FAS 60) net-premium benefit reserve with locked-in
  best-estimate assumptions and a provision for adverse deviation.

``NET_PREMIUM``, ``CRVM``, ``VM20``, and ``GAAP`` (FAS 60) are all implemented
for ``TermLife`` (ADR-087..092, ADR-127) and ``WholeLife`` (ADR-087..092,
ADR-128); no basis beyond ``NET_PREMIUM`` is implemented for the other products.
Each product declares the bases it supports; selecting an unimplemented basis
raises ``PolarisComputationError`` rather than silently falling back, so a
pricing run can never report a reserve on a basis the engine did not actually
compute.
"""

from enum import StrEnum

__all__ = ["ReserveBasis"]


class ReserveBasis(StrEnum):
    """The reserve valuation method applied across a projection run."""

    NET_PREMIUM = "NET_PREMIUM"
    CRVM = "CRVM"
    VM20 = "VM20"
    GAAP = "GAAP"
