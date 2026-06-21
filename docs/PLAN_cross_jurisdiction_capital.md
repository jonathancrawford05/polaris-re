# Plan — Cross-jurisdiction regulatory capital (Epic 3 / Tier-A A3)

> **Audience.** A new Claude Code session carrying this epic across several
> daily-dev runs. Read this document fully before writing code, then read the
> linked CLAUDE.md / ARCHITECTURE.md (§5 reinsurance, §7 analytics) /
> DECISIONS.md (ADR-047 / ADR-065 / ADR-072 on the existing LICAT capital
> module, ADR-048 on return-on-capital) sections. This plan is the read-only
> spec; the running log lives in
> `docs/CONTINUATION_cross_jurisdiction_capital.md`, the per-session
> `docs/DEV_SESSION_LOG_*` files, and the ADRs.
>
> **Status.** IN PROGRESS — Slice 1 shipped (US RBC core + `CapitalModel`
> protocol, ADR-098). Slices 2–4 planned below.
>
> **Source.** `docs/COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` Tier-A item
> **A3** (★★★★★ value, ~15 dev-days for both, the #3 unstarted epic, started
> after A1 Reserve-basis matching and A2 IFRS 17 movement shipped) and
> `docs/PRODUCT_DIRECTION_2026-06-18.md` IMPORTANT "Cross-jurisdiction
> regulatory capital (US RBC + Solvency II)" (restored from
> PRODUCT_DIRECTION_2026-04-19, was BLOCKER).

---

## 1. Goal

`analytics/capital.py` today computes **LICAT** required capital (OSFI's
Canadian standard: C-1 asset, C-2 insurance — mortality/lapse/morbidity —, C-3
interest-rate, summed). It is Canada-only. A reinsurer cannot evaluate a **US**
or **EU** deal on a return-on-capital basis — the primary decision metric — at
all today.

This epic adds the two missing jurisdictional capital standards as siblings of
`LICATCapital`, all three plugging into a shared `CapitalModel` protocol so
`ProfitTester.run_with_capital` (and every downstream RoC surface) works with
any jurisdiction:

1. **US RBC** (NAIC Life Risk-Based Capital) — the C-0…C-4 component model with
   the NAIC **covariance square-root** aggregation, and the Authorized Control
   Level (ACL) / Company Action Level (CAL) basis used for the RBC ratio.
2. **Solvency II SCR** (EU) — the modular SCR with life-underwriting / market /
   counterparty risk modules, **correlation-matrix** BSCR aggregation, and a
   cost-of-capital risk margin.

When complete, the engine can quote a deal under LICAT, US RBC, or Solvency II
and surface return-on-capital under whichever standard the cedant files.

## 2. Why this work, and what it does NOT do

**Why.** US RBC is a hard *market-access gate*: the 2026-04-19 baseline rated it
a BLOCKER, and the 2026-06-18 review restored it to IMPORTANT (Tier-A A3) at
maintainer direction. Reinsurers price US (largest market) and EU deals on a
return-on-capital basis; without RBC/SCR the engine cannot quote them.

**Does NOT.**

- It does **not** change `LICATCapital` / `CapitalResult` or any default LICAT
  numbers; the new modules are **additive** siblings and goldens stay
  byte-identical until the final surfacing slice (and even then only for runs
  that request a non-LICAT jurisdiction).
- It does **not** build a shock-based asset / ALM model. Like the LICAT module
  (ADR-047/072), these are **factor-based committee-stage approximations** with
  conservative, documented, overridable per-product factors. The full
  shock-based calibration is the C0 Asset/ALM epic (CVR Tier C, after A1–A3).
- It does **not** model tax, deferred-tax assets, or company-action-level
  interventions; it produces a required-capital *schedule* and the standard
  ratio denominators (ACL for RBC, SCR for Solvency II).

## 3. Decomposition (4 slices)

Each slice leaves all tests green, is independently mergeable, and keeps the
goldens byte-identical until the final surfacing slice.

### Slice 1 — US RBC core module + `CapitalModel` protocol  ✅ SHIPPED
- `analytics/capital_base.py`: `CapitalModel` and `CapitalSchedule` structural
  `Protocol`s capturing the shared calculator/result interface LICAT already
  satisfies (`required_capital(cashflows, nar) -> schedule`; schedule carries
  `capital_by_period` / `initial_capital` / `peak_capital` / `pv_capital` /
  `capital_strain` / `pv_capital_strain`). Small shared discount/strain helpers.
- `analytics/rbc.py`: `RBCFactors` (Pydantic, the nine NAIC component factors),
  `RBCResult` (component arrays + NAIC covariance aggregate + ACL/CAL, satisfies
  `CapitalSchedule`), `RBCCapital` calculator with `for_product` factor
  defaults, implementing the NAIC Life RBC **covariance square-root** formula.
- Tests: covariance closed form (`sqrt[(C1o+C3a)² + C2² + …] + C0 + C4a`);
  per-product factor defaults; ACL = ½ × CAL; CEDED rejection; NAR resolution
  and length validation; `capital_strain` / `pv_capital` mirror; both
  `RBCResult` and `CapitalResult` satisfy `CapitalSchedule`; both `RBCCapital`
  and `LICATCapital` satisfy `CapitalModel`.
- ADR-098. Goldens byte-identical (new module, nothing wired into pricing).

### Slice 2 — RBC ↔ ProfitTester integration + RBC ratio
- **Status:** NEXT
- Generalise `ProfitTester.run_with_capital` to accept the `CapitalModel`
  protocol instead of the concrete `LICATCapital` (signature widening only;
  LICAT callers unchanged → byte-identical). Add an `RBCResult.rbc_ratio(tac)`
  / ACL-denominator helper and a `ProfitResultWithCapital`-level RBC-ratio
  surface if it fits cleanly.
- Tests: `run_with_capital` produces identical metrics for a `LICATCapital` as
  today (regression); a parallel test drives it with an `RBCCapital`; RBC-ratio
  closed form (TAC / ACL).
- ADR-099. Goldens byte-identical (signature widening; LICAT path untouched).

### Slice 3 — Solvency II SCR module
- **Status:** PLANNED
- `analytics/solvency2.py`: `SolvencyIIFactors`, `SolvencyIIResult`,
  `SolvencyIICapital` — modular SCR (life underwriting: mortality / lapse /
  catastrophe sub-modules; market; counterparty), **correlation-matrix** BSCR
  aggregation (`sqrt(rᵀ · Corr · r)`), and a cost-of-capital **risk margin**.
  Satisfies `CapitalModel` / `CapitalSchedule`.
- Tests: BSCR correlation aggregation closed form against a 2×2 / 3×3 worked
  matrix; per-module factor defaults; risk-margin CoC; CEDED rejection.
- ADR-100. Goldens byte-identical (new module, nothing wired into pricing).

### Slice 4 — Surface the jurisdiction selector
- **Status:** PLANNED
- CLI `polaris price --capital {licat,rbc,solvency2}` (default `licat` →
  byte-identical); API `capital_model` field; Excel capital sheet jurisdiction
  label + ratio; dashboard selector; validation notebook comparing the three
  standards on the golden block. This is the surfacing slice (outputs move only
  for runs that explicitly request a non-LICAT jurisdiction).
- ADR-101. May rebaseline only the capital-surface goldens for non-default runs;
  the default `licat` path stays byte-identical.

## 4. Key constraints (from CLAUDE.md / ARCHITECTURE.md)

- Vectorised: capital schedules stay numpy `(T,)`; the per-component arithmetic
  and the covariance/correlation aggregation broadcast across the time
  dimension. No per-policy loops.
- Every capital aggregation gets a **closed-form verification test** (CLAUDE.md
  §5). The covariance (RBC) and correlation-matrix (SCR) aggregations are the
  defining formulas — each gets a worked-example test.
- No `Optional` / `List`; Python 3.12 typing. `float64` for monetary arrays.
- Do **not** hardcode the factor defaults in calculation paths — they live in
  per-product default tables and on the Pydantic `*Factors` model, overridable
  by the caller (CLAUDE.md §10 "Never hardcode assumptions"; mirrors LICAT).
- Sign convention matches LICAT: required capital is a positive, time-varying
  scalar, NOT discounted at the hurdle rate (the time-value adjustment lives in
  the RoC metric).
- Factors are **committee-stage approximations**, clearly documented as such in
  the module docstring and the ADR, with the shock-based calibration deferred to
  the C0 Asset/ALM epic — exactly the disposition the LICAT module uses.

## 5. Open design questions (resolve as the epic proceeds)

- **Held-capital basis for RoC.** US RBC defines several action levels. Slice 1
  uses **Company Action Level** (= the covariance result = 2× Authorized Control
  Level) as `capital_by_period`, the held-capital basis, and exposes ACL as the
  ratio denominator. Confirm with the maintainer whether a target multiple of
  ACL (reinsurers commonly hold 300–400% of ACL) should be configurable in
  Slice 2/4 rather than fixed at CAL.
- **NAIC factor vintage.** Slice 1 uses the classic pre-2021 Life RBC covariance
  grouping and NAIC-order C-1o / C-2 / C-3 factors as committee approximations.
  The 2021+ bond-factor expansion (20 NAIC designations) and the C-3 Phase II
  stochastic requirement are out of scope (asset-model work).
- **Solvency II correlation matrix.** Slice 3 must pick the standard-formula
  correlation matrices (life-underwriting sub-modules, top-level BSCR). Use the
  Delegated Regulation standard-formula matrices; document the vintage in
  ADR-100.
- **Currency.** All three modules are currency-agnostic (factors × dollar
  reserves/NAR). Multi-currency books are out of scope.
