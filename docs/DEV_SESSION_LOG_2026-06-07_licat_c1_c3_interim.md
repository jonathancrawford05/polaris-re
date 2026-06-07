# Dev Session Log — 2026-06-07

## Item Selected
- **Source:** PRODUCT_DIRECTION_2026-05-23.md — Promoted Follow-ups
- **Provenance:** CONTINUATION_licat_capital — Open Question #3
- **Priority:** NICE-TO-HAVE
- **Title:** LICAT C-1 and C-3 capital components (interim)
- **Slice:** complete (SMALL item — single session)

## Selection Rationale

All six `CONTINUATION_*.md` files are COMPLETE, so no in-progress
multi-session feature claimed this session. From the
`PRODUCT_DIRECTION_2026-05-23.md` "Items explicitly safe for next-session
pick-up" list:

- **Ingestion strict-mode for unknown rating codes** — shipped on main
  (ADR-071, commit b470ff4, PR #58). Pruned from PRODUCT_DIRECTION as
  part of this session. See PRUNE section below.
- **LICAT C-1 / C-3 interim factor** — picked because:
  - SMALL (single file extension + tests + ADR, no contract changes).
  - Self-contained (extends `analytics/capital.py`; opt-in only).
  - Backward-compatible by construction (`for_product` and
    `for_product_extended` keep C-1 / C-3 at zero; the new
    `for_product_interim` is a separate classmethod).
  - Closes a long-standing committee-credibility gap flagged in
    `CONTINUATION_licat_capital` Open Question #3.

Items not picked and why:
- **Dashboard / dimension-outer follow-ups (ADR-069 derivatives)** —
  PR #56 is merged now, so these are technically unblocked, but the
  dashboard portfolio view they ride along with does not exist yet,
  so the work would be premature.
- **`yrt_rate_table_path` on DealConfig** — touches `DealConfig` schema
  + CLI + tests; slightly larger surface than capital extension.
- **Per-duration cell-failure interpolation / warm-start brentq** —
  both pure rate-schedule polish; lower deal-committee impact than
  the LICAT capital number completeness.
- **Gross / ceded cash flow sheets in deal-pricing Excel** — touches
  the Excel writer plus DTO fields; would defer a decision on
  whether the deal committee actually wants the three-sheet section.
- **`polaris price --with-sensitivity`** — couples CLI `price` to
  scenarios + Excel sensitivity sheet; touches three modules.
- **Treaty-level rated-YRT override** — would need cedant input on
  whether the override matches industry practice; better deferred
  until ingestion confirms a real case.

## PRUNE (step 6 sanity)

`PRODUCT_DIRECTION_2026-05-23.md` line 250 entry "Ingestion strict-
mode for unknown rating codes" has been **closed by inspection**:
already shipped via ADR-071 / PR #58 / commit b470ff4 on main. The
entry has been crossed out in place (matching the convention used
for the other shipped Promoted Follow-ups) with the shipping ADR /
PR / commit recorded; the line is also removed from the "explicitly
safe for next-session pick-up" enumeration. The full entry text is
preserved for audit trail.

All other entries in the active queue were verified against `git log
main` and the latest COMPLETE CONTINUATIONs — none are stale.

## What Was Done

Added `LICATCapital.for_product_interim(product_type)` — a new
classmethod that populates all five LICAT factors with conservative
committee-stage placeholders. The C-2 schedule is identical to
`for_product_extended` (mortality + lapse + morbidity, per
ADR-065). The interim additions are:

- **C-1 asset default:** uniform 0.005 (0.5% of reserves) across
  every product type. An investment-grade portfolio default-risk
  loading that does not differ materially by liability product in
  the committee-screening regime.
- **C-3 interest rate:** scales with effective reserve duration —
  TERM 0.5%, WL 1.0%, UL 1.5%, ANNUITY 2.0%, DI / CI 0.5%. The
  schedule mirrors the qualitative duration ordering deal committees
  expect; absolute levels (50-200 bps of reserves) are intentionally
  conservative placeholders until Phase 5.4's shock-based engine
  replaces them with KRD-driven numbers.

Naming is `for_product_interim` (not `for_product_full`) so the
placeholder status is explicit at the call site: readers see "this
is a stop-gap until Phase 5.4 lands" rather than mistaking it for
the definitive LICAT calculation.

The constructor is opt-in only. Every existing capital surface
(ADR-049 CLI `--capital licat`, FastAPI `capital_model="licat"`,
dashboard checkbox, Excel `_CAPITAL_METRICS` rows) continues to use
`for_product(...)` and produces byte-identical numbers — confirmed
by the unchanged golden regression on `golden_inforce.csv` +
`golden_config_flat.json`.

Switching the standard surfaces to `for_product_interim` is a
deliberate follow-up that requires golden baseline regeneration and
its own ADR; the Out-of-scope section of ADR-072 names it explicitly
so the next session can pick it up if the deal committee asks for
the interim factors in the standard output.

## Files Changed
- `src/polaris_re/analytics/capital.py` — module docstring refresh;
  added `_C1_INTERIM_DEFAULT_BY_PRODUCT` and
  `_C3_INTERIM_DEFAULT_BY_PRODUCT` constants; added
  `LICATCapital.for_product_interim` classmethod. ~+55 lines.
- `tests/test_analytics/test_capital.py` — added
  `TestForProductInterim`, `TestForProductInterimBackwardCompat`,
  `TestForProductInterimAppliesToCapital`. ~+170 lines, 30 new
  tests (16 parametrised cases).
- `docs/DECISIONS.md` — appended ADR-072.
- `docs/PRODUCT_DIRECTION_2026-05-23.md` — crossed out the shipped
  "Ingestion strict-mode for unknown rating codes" entry (ADR-071
  PRUNE) and the just-shipped "LICAT C-1 and C-3 capital components
  (interim)" entry (ADR-072); updated the "explicitly safe for
  next-session pick-up" enumeration to reflect both closures.
- `docs/DEV_SESSION_LOG_2026-06-07_licat_c1_c3_interim.md` — this
  file.

## Tests Added
- `TestForProductInterim::test_interim_preserves_extended_c2_factors_per_product`
  (6 parametrised cases — one per ProductType).
- `TestForProductInterim::test_interim_c1_c3_factors_per_product`
  (6 parametrised cases verifying the interim C-1 / C-3 schedule).
- `TestForProductInterim::test_interim_annuity_has_highest_c3`
  (qualitative ordering check: ANNUITY > WL > TERM).
- `TestForProductInterim::test_interim_c1_uniform_across_products`
  (asserts the uniform-0.5% C-1 invariant across every ProductType).
- `TestForProductInterimBackwardCompat::test_for_product_c1_c3_remain_zero`
  (6 parametrised cases — confirms `for_product` is unchanged).
- `TestForProductInterimBackwardCompat::test_for_product_extended_c1_c3_remain_zero`
  (6 parametrised cases — confirms `for_product_extended` is unchanged).
- `TestForProductInterimAppliesToCapital::test_term_interim_c1_and_c3_applied`
  (closed-form check: TERM C-1 = 0.005 * 100K = 500; C-3 = 0.005 *
  100K = 500).
- `TestForProductInterimAppliesToCapital::test_annuity_interim_c3_largest`
  (closed-form check: ANNUITY C-3 = 0.02 * 1M = 20K).
- `TestForProductInterimAppliesToCapital::test_interim_capital_sums_all_five_components`
  (closed-form check: full WL interim breakdown sums correctly).
- `TestForProductInterimAppliesToCapital::test_interim_increases_capital_vs_extended`
  (sanity check: interim > extended by exactly the C-1 + C-3
  contribution, on a per-period basis).

Total: 30 new tests (16 parametrised cases across 6 ProductTypes +
4 closed-form arithmetic checks + 4 backward-compat sweeps).

Closed-form verification per CLAUDE.md §5 is provided by the
`TestForProductInterimAppliesToCapital` class — each test computes
an expected value by hand from the factor schedule and the reserve /
NAR vectors, then asserts equality via
`np.testing.assert_allclose`.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| New `for_product_interim(product_type)` constructor exists | OK | Returns `LICATCapital` with all five factors populated |
| C-1 factor is uniform 0.5% across every ProductType | OK | Asserted by `test_interim_c1_uniform_across_products` |
| C-3 factor scales with duration (ANNUITY > UL > WL > TERM) | OK | Asserted by `test_interim_annuity_has_highest_c3` |
| `for_product` and `for_product_extended` C-1 / C-3 unchanged | OK | 12 parametrised backward-compat tests pass |
| Golden regression unchanged (`golden_inforce.csv` + `golden_config_flat.json`) | OK | Cedant PV $3,513,563; Reinsurer PV $45,386 — both bit-identical |
| ADR-072 added to `docs/DECISIONS.md` | OK | Full ADR with calibration rationale, factor schedule, Out-of-scope list |
| Test suite green (`make test`, `tests/qa/`) | OK | 1204 passed / 87 deselected; QA suite 40 / 40 |
| Ruff format + check pass | OK | `All checks passed!` |

## Open Questions / Follow-ups

1. **Should the standard CLI / API / dashboard / Excel capital
   surfaces switch from `for_product` to `for_product_interim` by
   default?** This is a behaviour change — every capital tile and
   every golden capital number would move. The right time is when
   the deal committee explicitly requests the interim factors in
   the standard output, paired with a baseline-regeneration ADR.
   Flagged in ADR-072 Out of scope.

2. **C-1 calibration uniformity.** The schedule sets C-1 = 0.005
   uniformly across product types on the rationale that the asset
   mix backing life reserves does not differ materially by liability
   product in the committee-screening regime. If a cedant provides
   asset portfolio composition, a finer C-1 (high-grade vs lower-
   grade weighted average) is a per-cedant calibration follow-up.

3. **C-3 calibration anchor.** The 50-200 bps range mirrors the
   qualitative duration ordering committees expect, but the absolute
   levels are placeholders. A QA-loop ADR benchmarking against
   published OSFI factor disclosures would tighten the schedule
   without changing the structure.

## Impact on Golden Baselines

None. `polaris price` on the golden inforce + config still returns
Cedant PV = $3,513,563 and Reinsurer PV = $45,386 — bit-identical
to pre-ADR-072 output. The interim factors only affect the capital
number when the caller explicitly invokes `for_product_interim`;
every existing surface continues to use `for_product(...)`.
