# Session log — 2026-08-25 — parity recalibration, criterion localisation, Anchor 2 measured

**Routine:** none. **Maintainer-directed session**, not a `ROUTINE_MGCV_PARITY.md`
pick — the maintainer asked for a recalibration after PR #212 on the reading that
*"development has completely stalled"*.
**Slice:** none designated. Registers PLAN slice 5c as an output.
**PR:** #213. **ADR:** none — nothing here is tier 3, so nothing is ADR-eligible yet.

**Maintainer authorization, verbatim:**

> *"Okay, I am thinking to take a step back to recalibrate the parity flow, I feel
> development has completely stalled and I will need to surface candidate root
> causes before I move to get us back on a fruitful path."*

> *"Go ahead and run it now then move to a recalibration note."*

> *"Yes, open the PR but include the proposed anchor 2 measurement so we can start
> to remedy one of the causes for slower than expected progress."*

> *"[Wood paper attached] please add 5c but include the Wood details to enable the
> fix."*

---

## Oracle version

**Tier 1 only, for every measurement in this session.** R 4.3.3 / mgcv 1.9.1 (local
apt), `OPENBLAS_NUM_THREADS=1`. Matches the routine's expected apt versions — no
drift to flag.

**No tier-3 dispatch was run.** Every figure below is therefore a **hypothesis, not
a result**, and none of them may enter `DECISIONS.md`, `PLAN_*`, `CONTINUATION_*` or
a docstring. This was got wrong on the first push and corrected after review — see
"Corrections" below.

## Gap before

- Slice 5b DONE (ADR-208). Its §4 registered prediction REFUTED at both tiers.
- The `sp`-dependent criterion discrepancy: **CONFIRMED at tier 3, unlocalised.**
  ADR-208's amendment named Wood (2011) §3.1 as the next hypothesis, untested.
- Slice 6 BLOCKED on it.
- **Anchor 2's primary metric (the MI contrast): never measured.** Zero occurrences
  in `CONFORMANCE_LEDGER.md` in six weeks.
- Test baseline on `origin/main` at session start: not separately recorded; this
  branch measures **3588 passed, 14 skipped, 0 failed** (review environment,
  `cecd5ce`).

## Hypotheses tried

**H1 — the criterion and ours differ as functions of `sp`, or they differ only by a
constant.** Discriminated by evaluating both at the SAME fixed `sp` at eight
well-separated points, which removes the optimiser entirely. **Result: they differ.**
The difference is not constant. → the discrepancy is in the criterion, not the search.

**H2 — the varying difference is a rank decision flipping, not a wrong formula
term.** Predicted from the shape (discrete departures, not smooth drift) and from
which points depart (only where λ's span many decades). Tested by reading the rank of
`S = Σλⱼ Sⱼ` at three tolerances. **Result: confirmed.** True rank 81; stable at
`1e-12` and `eps·p` at every point; 79–80 at the shipped `1e-10` at exactly the
departing points.

**H3 — the tolerance CAUSES the discrepancy rather than correlating with it.**
Tested by applying only the null-space correction analytically. **Result: confirmed**
— the spread collapses by three orders of magnitude and ADR-208's ranking flip
disappears.

**H4 — Anchor 2's primary metric cannot be measured without a prediction grid**
(ADR-206's stated reason, inherited by ADR-208). **Result: REFUTED.** `StudyYear_C`
enters only through `s(AttdAge, by=StudyYear_C)`, whose contribution is linear in the
by variable, so `η(age, sy+1) − η(age, sy) = f(age)` exactly. The contrast cancels the
intercept, the reference smooth and `ti()` and collapses to the by-term's own smooth,
available on the training rows with no new machinery. The grid is needed for Anchor
2's *full* definition, not for the metric.

## Gap after

- The criterion discrepancy is **localised to `log|S|₊`'s null-space cut** at tier 1,
  with a demonstrated cause and Wood's own name for the mechanism ("numerical zero
  leakage"). Not closed — no fix implemented.
- **Anchor 2's primary metric has a value** for the first time, at tier 1, on the
  training design.
- Slice 6 still BLOCKED; the route out is registered as slice 5c.
- Figures: `docs/RECALIBRATION_mgcv_parity_2026-08-25.md` §1 and §4.1. Reproduce with
  `scripts/gam_fixed_sp_score_probe.R` + `_compare.py` and
  `scripts/gam_mi_contrast_probe.R` + `_compare.py`.

## Provenance (ADR-193) — per comparison, per column

| Comparison | Quantity | Left producer | Right producer | Class |
|---|---|---|---|---|
| MI contrast (§4.1) | `mi_contrast` | `gam_mi_contrast_compare.py`: own `assemble_model_design` + `penalized_irls_general`, then `X[:, by] @ coef[by] / StudyYear_C` | `gam_mi_contrast_probe.R`: `predict(m, type="terms")[, by] / StudyYear_C` | **INDEPENDENT** |
| MI contrast (§4.1) | `eta` | same Polaris fit | `predict(m, type="link")` | **INDEPENDENT** |
| Fixed-`sp` score (§1) | REML criterion at fixed `sp` | `gam_reml.reml_score_general` | `m$gcv.ubre` | **DIAGNOSTIC** — reports a discrepancy, ticks no criterion, declares no claim |

**Mechanical test on the signature.** `gam_mi_contrast_compare.py` reads only
`AttdAge` / `PolYear` / `StudyYear_C` / `ExposCnt` / `y`, the knots and `sp_fixed`
from the payload — all shared *inputs* — and never reads `payload["mi_contrast"]`
into the computation, only into the diff. `8.805e-13` is not a tautology's zero.

**The `sp` asymmetry.** In §4.1 `sp` is a **shared input** supplied to both sides
(ADR-206's arrangement), deliberately, so the contrast measurement is isolated from
the separate free-`sp` selection gap. It is *not* a compared quantity here.

**Neither measurement is a committed conformance case.** No `VerificationClaim`
backs either table, so per `CLAUDE.md` both are reported as diagnostic readings
rather than parity evidence. The MI contrast is *promotable* — its provenance is
genuinely INDEPENDENT — and doing so needs a conformance module with an
`evidence_markdown()` headline plus tier 3.

## Corrections made this session

- **The first push wrote tier-1 figures into `CONTINUATION_*.md` and `PLAN_*.md`**,
  which `ROUTINE_MGCV_PARITY.md` reserves for tier 3 — and the PR body stated that
  rule verbatim while the diff broke it. Caught by PR #213 review [P0]. Fixed by
  keeping every figure in the recalibration note (a tier-1 session record) and having
  both files reference it qualitatively, with slice 5c's prediction and definition of
  done rephrased against its own tier-3 re-measurement.
- **Slice 5c's sequencing step 1 described the tier-3 confirmation as "a CI dispatch
  of an existing probe."** It is not — the Python side and a workflow step did not
  exist. Fixed: the Python side is now committed
  (`scripts/gam_fixed_sp_score_compare.py`), and step 1 names the workflow step as
  outstanding work to budget for.
- **The recalibration's cause 3.1 first read as neglect** ("never measured, nobody
  bothered"). H4 showed the real cause is sharper and more useful: a capability gap
  correctly identified once, then inherited as a reason not to measure, with three
  ADRs restating the blocker and none re-deriving whether the metric needed it.

## Not done

- No tier-3 dispatch of either measurement.
- No fix implemented — slice 5c is registered, not executed.
- Anchor 2's pinned prediction grid — the contrast is measured on the training design
  only, a partial delivery.
- The five recalibration proposals are maintainer decisions; none adopted.
