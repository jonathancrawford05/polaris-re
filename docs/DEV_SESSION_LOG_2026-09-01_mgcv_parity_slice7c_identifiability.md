# Session log — 2026-09-01 — Slice 7c: is the `log10(sp)` gate reachable at all?

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 7c — `docs/PLAN_mgcv_parity_engine.md`. Drafted as a PROPOSAL in
the PR #223 review conversation (the reviewer declined to self-register it,
because Part 2 bears on "whether to relax an acceptance criterion" —
`ROUTINE_MGCV_PARITY.md`'s "May not decide" — and Part 1 would change every
`fit_polaris_gam` caller's search, an Anchor 7 question). **The maintainer
registered it in that same conversation ("proceed with the slice"), the same
in-session mechanism ADR-218 records for slice 7b.**
**PR:** `claude/brave-keller-u947z0` (this session's designated branch).
**ADR:** ADR-219.

## Setup

- `uv sync --all-extras` — clean.
- Installed the tier-1 scratch oracle: `apt-get install -y -qq
  --no-install-recommends r-base-core r-cran-mgcv r-cran-jsonlite`
  (`--no-install-recommends` needed — the default pulls a mesa/va-driver
  chain that 404s in this image). **R 4.3.3 (2024-02-29) / mgcv 1.9-1**,
  matching the routine's expected apt versions, no drift.
- Read `ROUTINE_MGCV_PARITY.md`, `VERIFICATION_STANDARD.md`, the slice 7c
  draft, ADR-193/196/201/202/209/211/212/213/217/218, and
  `gam_derivatives.py`/`gam_reml.py`/`gam_reml_optimize.py` source.

## Baseline

Two configurations, and the difference between them matters — recorded in
full because a single number here would have been misleading:

- **Before R was installed** (R-gated tests SKIPPED), on the merged base:
  **3551 passed, 0 failed, 17 skipped, 126 deselected.** No mortality-table
  failures — setup step 2's `convert_soa_tables.py` was run, which clears the
  5 that other sessions record as standing.
- **After R was installed** (R-gated tests RUN), on this branch:
  **3574 passed, 1 failed, 3 skipped, 126 deselected.**

**The one failure is PRE-EXISTING on `main`, and was verified there directly
rather than assumed:** `test_gam_model_conformance.py::test_the_r_probe_runs_
end_to_end` fails at `assert comparison.converged` with
`max_abs_eta_diff=0.000759342158123566`,
`max_abs_log10_sp_diff=0.2606175963459325` — and reproduces on `origin/main`
(`0fd6ddc`) **to the last printed digit**, with this session's changes absent.
It is not the flake ADR-218's own log records for this test (that one passed
in isolation; this one fails in isolation too, deterministically).

**Root cause, measured not guessed:** it is ADR-211/213's own
`OPENBLAS_NUM_THREADS` sensitivity. This container's default is 4 threads
(`nproc=4`, variable unset), the count ADR-213's ledger row already records as
the one where the blind single-start free-`sp` fit FAILS to converge. Pinning
it reverses the result on `main`, unchanged code:

| `OPENBLAS_NUM_THREADS` | result on `origin/main` |
|---|---|
| unset (4 threads, the container default) | **FAILED** |
| `1` (what CI's compare job pins, PR #217 review [P1-1]) | **passed** |

So CI is green because the workflow pins threads job-level, while any
contributor running the suite locally with default threads sees a red test.
That is a real gap, it is **out of this slice's scope**, and it is filed as a
promoted follow-up rather than folded in or silently noted (DISCOVERY
protocol) — see "Follow-ups filed".

## Gap Before

ADR-218 closed slice 7b with `max_abs_log10_sp_diff = 1.48` against a `1e-2`
gate, attributed it to optimiser convergence on a weakly-identified surface,
and named an analytic REML gradient as the next hypothesis. **Tier and digest
of the "before":** tier 3, ADR-218, CI run 33458654272 — `1.4754` with
`multistart=True`.

## Registered prediction (written before any measurement, PLAN slice 7c)

The analytic gradient closes the SCORE gap to at or below the objective's own
noise floor, but `max_abs_log10_sp_diff` stays O(1) because the direction is
not identified — making the metric question decidable on evidence. If instead
the gate closes to `1e-2`, the prediction is refuted and that is the more
valuable outcome.

## Hypotheses tried

### Pass 1 — Part 0: is the gate reachable? (the gate the slice put in front of itself)

**Hypothesis:** some of the 7 `rho` directions are not resolved by our own
criterion at all, in which case no optimiser can close a `1e-2` gate on them.

**Built:** `scripts/gam_select_free_sp_identifiability_diagnostic.py` —
eigenspectrum of the REML Hessian w.r.t. `rho` at `mgcv`'s own point (reusing
the already-`mgcv`-checked `finite_difference_rho_hessian`), plus a
step-stability scan and a per-block profile. No production code touched.

**Measured (tier 1):** eigenvalue-sign count read **5 of 7** — a number that
later FAILED tier-3 re-measurement and is retracted (see "Tier-3 confirmation"
below). The robust reading, confirmed at both tiers, is that **2 of 7
directions carry no resolvable curvature.** The two exceptions
load on `b1` (`s(AttdAge)` existing) and `b3` (`s(AttdAge,by=StudyYear_C)`
existing) with raw eigenvalues `-0.0087` and `-0.0035` — **exactly the two
blocks ADR-218 reported the residual had relocated to.**

**Verdict:** provisionally decisive, pending pass 2 — a negative eigenvalue
could be a genuine saddle rather than a flat direction, and the two readings
demand different conclusions.

### Pass 2 — saddle, or noise floor on a flat direction?

**Hypothesis:** the negatives are numerical. A real curvature is stable as the
step shrinks; a constant absolute noise floor divided by `h^2` grows like
`1/h^2`. (The same discriminator ADR-212 used for the finite-difference-step
defect.)

**Measured (tier 1):**

| block | h=0.2 | h=0.1 | h=0.05 | h=0.025 | reading |
|---|---:|---:|---:|---:|---|
| b1 | -0.00088 | -0.00324 | -0.01369 | -0.08094 | FLAT (noise) |
| b3 | -0.00020 | -0.00234 | -0.01042 | -0.02382 | FLAT (noise) |
| b5 | 1.57935 | 1.57766 | 1.57380 | 1.54281 | identified |
| b6 | 1.28503 | 1.28156 | 1.27370 | 1.22681 | identified |

`b1`/`b3` grow like `1/h^2`; the identified blocks are stable to ~2% across
the same 8x range. The per-block profile says it without Hessians: moving `b3`
(at `log10(sp) = 11.70`) **two decades up** changes the score by `-0.0002`,
and one decade either way by under `2e-4`, against `~+1.0` for HALF a decade
on `b5`.

**Verdict: DECISIVE. The gate is ILL-POSED, not merely hard.** No optimiser,
however exact, can pin a parameter the objective does not resolve across two
decades. **Stated here before Part 1 was considered, per the slice's own DoD
— and it is what stopped Part 1 being built.**

### Pass 3 — Part 2: which metric actually tracks the agreement?

**Built:** `src/polaris_re/analytics/gam_sp_identifiability.py`
(`hessian_weighted_distance`, `identified_direction_count`), verified against
closed forms — identity Hessian reduces to the Euclidean norm, diagonal
Hessian to a hand-computed quadratic form, plus rotation invariance — never
against another implementation of itself.

**Measured (tier 1):**

| search | `max abs log10(sp) diff` | H-weighted | score gap |
|---|---:|---:|---:|
| single-start | 5.1320 | 7.9265 | 5.9595 |
| `multistart=True, n_starts=9` | 1.4754 | 0.0617 | 0.0141 |
| improvement | **3.5x** | **128x** | **424x** |

The recomputed score gap `0.014057` reproduces ADR-218's warm-start `0.0141`
independently — a cross-check on both.

**Verdict:** the committed gate credits multistart with `3.5x` for a change
the criterion-aware metrics score at `128x`-`424x`, because it keeps measuring
the two directions the criterion cannot resolve. **Recommended: the H-weighted
distance, on ADR-193 grounds** — same two independent operands, re-normed, so
INDEPENDENT provenance survives; the sharper-looking score gap is DIAGNOSTIC
(our criterion at a point `mgcv` supplied) and must never be a gate.
**Recommended, NOT taken.** Three passes, three informative results — stopped
here per the routine's own three-passes guardrail.

## Gap After

The gap ADR-218 left is **dissolved rather than closed**: on `b1`/`b3` there
was never a closable gap, because the criterion does not distinguish those
values. On the 5 directions it does resolve, the disagreement is `0.0617`
(H-weighted) / `0.0141` (score), both already small.

`max_abs_log10_sp_diff` is unchanged at `1.4754` and **the committed `1e-2`
gate still reads `agrees=False`** — untouched and un-widened (Anchor 8). What
changed is the evidence about what that number means.

## Provenance (ADR-193)

**This slice publishes no parity comparison, deliberately.** Part 0's
eigenspectrum, step scan and profile are properties of our OWN criterion, with
`mgcv`'s selection as the POINT of evaluation — an argument, not an operand.
No second producer exists to name, so the measurement is **neither INDEPENDENT
nor ECHO/TRANSPORT**: those labels classify comparisons and this is not one.
The three ledger rows carry the third category, `MEASUREMENT (own
criterion)` — codified at `docs/VERIFICATION_STANDARD.md` §2.1 by ADR-219
amendment 1, after review round 1 observed that a BLANK label is
indistinguishable from a forgotten one.

Part 2's table is mixed by column, which is the substance of its
recommendation: `max abs log10(sp) diff` INDEPENDENT (unchanged from ADR-218),
H-weighted INDEPENDENT (same operands, different norm), score gap DIAGNOSTIC.

## Oracle version

Tier 1: R 4.3.3 / mgcv 1.9-1 (local apt), matching the routine's expected
versions — no drift. **Tier 3 NOT dispatched, and the ADR/ledger say so.**
This slice changes no production code path for a tier-3 run to exercise, and
ADR-218's own tier-3 readings for these quantities are hours old and
unchanged. Per `ROUTINE_MGCV_PARITY.md` step 2 the rows are marked tier 1 and
**may not be cited outside this session log without a tier-3 confirmation.**

## Quality gate

- `uv run ruff format src/ tests/ scripts/` — clean.
- `uv run ruff check src/ tests/` — clean. `scripts/` retains the same 12
  pre-existing errors, none in a file this session touched (verified).
- `uv run pytest tests/test_analytics/test_gam_sp_identifiability.py -q` —
  **9 passed** (all closed-form).
- Full suite — **3574 passed, 1 failed, 3 skipped**; the single failure is
  pre-existing on `main` and thread-count-induced, established above.
- `tests/qa/golden_outputs/` byte-identical — this session touches no path any
  golden depends on.

## Perf history

`uv run python scripts/perf_history.py` — one row appended for this branch's
HEAD commit (ADR-177 step 14b, initial PR open), append-only, no prior row
touched. Verdict: `has_structural_creep=False`; `has_wall_time_creep=True`
(recent/baseline ratio 1.338x on the `TermLife.project` probe) — **the same
1.338x ADR-218 recorded hours earlier**, i.e. unchanged run-to-run variance on
a probe entirely unrelated to this GAM-only, no-production-path-changed
session, not a fresh signal from it.

## Definition of done

Recorded inline against each criterion in `PLAN_mgcv_parity_engine.md` slice
7c, including **three `[machine]` criteria WITHDRAWN** when Part 0's gate
fired. They are struck through with the reason, not deleted, and carried
verbatim into slice 7d — the gate working as designed ("Part 0 … may end the
slice"), not criteria quietly failed.

## PR #224 review response, round 1

All three findings accepted and fixed; none disputed.

- **[P1-1] the slice 7c DoD duplicated a criterion and misfiled its evidence
  — CORRECT, and self-inflicted.** The edit that recorded the outcomes began
  its replacement one bullet too low, so the `**MET**` intended for the
  `[machine]` eigenspectrum criterion landed under the pre-existing
  `[judgement]` line, which was then rewritten — leaving a duplicated
  `[judgement]` and a `[machine]` criterion with no verdict beside it. The
  reviewer's framing is right that this is what a quietly-dropped criterion
  also looks like. Fixed: duplicate removed, `MET` moved under the `[machine]`
  line, **six → three** ledger rows corrected (six was copied from slice 7b's
  count), and the **stiff/flat ratio the criterion explicitly asks for** now
  stated — `>= 190` on eigenvalues, `~1.8e3` on the coarsest diagonal
  readings, given as a lower bound because the denominator is a noise floor,
  which is itself the finding.
- **[P2-1] the Part 2 table's provenance travelled only in prose — CORRECT.**
  Recorded as two binding preconditions in ADR-219 and on slice 7d, so they
  cannot be lost between the ADR and the work: the H-weighted distance must be
  a declared `ComparedQuantity` before it gates anything, and — the reviewer's
  sharper point, which genuinely qualifies this ADR's INDEPENDENT label — the
  **weighting Hessian must be evaluated at OUR OWN point, not `mgcv`'s.** Both
  operands are independently produced, but weighting at `mgcv`'s point lets its
  payload re-enter through the norm as a second channel. Not a live
  mislabelling (nothing gates on it, and provenance classifies the operands),
  but a real seam, and closing it is cheap.
- **[P2-2] bare float `==` at `test_gam_sp_identifiability.py:39` — CORRECT.**
  Exactness genuinely is the contract there, but the convention holds anyway;
  now `assert_allclose(..., rtol=0.0, atol=0.0)`, which states the same
  contract inside the rule.

## Tier-3 confirmation (2026-09-02) — and the two things it refuted

Amendment 1 wired the diagnostic into `mgcv-conformance.yml` so the next tier-3
run would confirm the eigenspectrum "for free". It ran on the very next push
(CI run 33633783477, R 4.6.1 / mgcv 1.9.4) **and refuted two published
numbers.** Recorded here as retractions, not quiet edits.

**Confirmed — the substantive finding, unchanged.** `mgcv`'s point is identical
across tiers (`b1` `10.2964`, `b3` `11.7046`), the profile is identical to three
decimals (`b3` +2 decades: `-0.000188` vs `-0.000219`), and step-stability calls
`b1`/`b3` FLAT at both tiers. **The gate is ill-posed, confirmed at two tiers**,
and not building the gradient stands. Amendment 1 decision 1's argument — that
`mgcv`'s selection does not move between 1.9-1 and 1.9.4 — is vindicated.

**Retraction 1: "5 identified directions of 7".** At tier 3 all seven
eigenvalues are positive (`+0.005624`, `+0.012057`, …), so the sign count reads
**7 of 7**. Same fixture. The number counted the *sign* of a quantity this
session's own step-stability scan had already shown to be noise — publishing it
as a headline was the error, not the disagreement. Fixed structurally:
`identified_direction_count` now REQUIRES an explicit `floor`, so a sign count
cannot be taken by accident, and the script derives its headline from
step-stability. Robust statement: **2 of 7 directions carry no resolvable
curvature**, both tiers.

**Retraction 2: the Part 2 improvement ratios.**

| metric | tier 1 | tier 3 |
|---|---|---|
| `max abs log10(sp) diff` | 3.5x better | **0.8x — WORSE** |
| H-weighted | 128x | 3.3x |
| score gap | 423x | 261x |

The Hessian, profile and `mgcv` point are stable, so the divergence is in **our
own free-`sp` search** — ADR-211/213's BLAS-environment sensitivity, dominating
the multistart row even with threads pinned on both sides. `3.5x / 128x / 424x`
is withdrawn as a tier-1 artefact.

**The conclusion survives and tier 3 sharpens it.** At tier 3 the committed gate
calls multistart a *regression* (`4.64 → 5.95`) on a change whose score gap
closed **261x**. A metric that reports a 261-fold criterion improvement as a
regression is measuring where the optimiser stopped, not the model. The reading
that disagreed with us made the case better than the one that agreed.

## Maintainer decisions, round 2 (2026-09-02) — ADR-219 amendment 1

All four open items resolved in conversation. Three implemented here; one
registered as its own slice because it edits a committed acceptance criterion.

1. **Tier-1 status accepted.** The diagnostic is now wired into
   `mgcv-conformance.yml` so the next tier-3 run confirms the eigenspectrum for
   free — the residual risk being that the reading is taken *at `mgcv`'s
   selected point*, which is version-dependent in principle. Bounded by
   evidence already held: ADR-218's tier-1 and tier-3 readings of this fixture
   agree to four significant figures.
2. **Provenance precedent ratified AND upgraded.** Not left as a precedent —
   codified as `VERIFICATION_STANDARD.md` §2.1, a third category
   `MEASUREMENT (own criterion)` with its own mechanical test ("remove the
   reference entirely — is there still a number?"). The three ledger rows now
   carry that label explicitly instead of a bare absence, because an unlabelled
   row is indistinguishable from a forgotten one.
3. **Slice 7d accepted, ranking left open.** Its headline justification is
   gone; what remains is real but not urgent, and should be ranked rather than
   inherit "next" by adjacency.
4. **Re-gating accepted, WITH THE METRIC CHANGED from this slice's own
   recommendation.** Not H-weighted primary. `eta`/`edf` primary, H-weighted as
   the `sp`-space companion — because provenance constrains what MAY gate, not
   what SHOULD, and a pricing engine's users care whether the fitted surface
   matches. Registered as **slice 7e**, not implemented here.

### The marketing constraint, recorded because it was not previously written down

The maintainer noted that `mgcv` parity is intended as a **marketing benchmark**
once development progresses far enough, and asked that we make sure parity can
be reached rapidly. That is a material design input and it makes slice 7e *more*
delicate rather than less:

- **It must narrow the claim, never loosen the measurement.** Changing an
  acceptance criterion to one the engine passes more easily, in service of a
  marketed claim, is structurally the move Anchor 8 forbids — even though this
  particular change is right on the merits. The defence is that the claim gets
  *smaller and more precise*, not that the evidence is good.
- **No unqualified "mgcv parity" claim, now or after 7e.** Conformance level 4
  genuinely DISAGREES (ADR-190) and `VERIFICATION_STANDARD.md` §5 records that
  this disagreement is real *because* levels 1-5 carry INDEPENDENT provenance.
  An unqualified claim would be refuted by our own committed ledger — the worst
  way for a public claim to fail.
- **"Rapidly" is a schedule target, not an input to a verification standard.**
  Named in advance rather than discovered later: where speed and defensibility
  conflict, the standard wins, because the fastest route to a claim that must
  later be retracted is not fast.

## Follow-ups filed

- **Slice 7d registered** (`PLAN_mgcv_parity_engine.md`) — the analytic REML
  gradient, re-aimed at the score gap on the identified directions, the
  `converged=False` defect and the ~8x cost saving; explicitly NOT at the
  `log10(sp)` gate. *1st-order — the direct continuation of ADR-218's own
  named next hypothesis, corrected by this slice's evidence.*
- **The `dw_deta` Fisher/observed hazard** — recorded in ADR-219 and on slice
  7d, so 7d does not wire `dw_drho` into a `cloglog` gradient and get a
  silently wrong answer. *1st-order — a defect-in-waiting this slice found in
  existing committed code.*
- **The re-gating decision itself** — recommended (H-weighted distance) and
  explicitly not taken; stays maintainer-reserved. *2nd-order — a
  comparator-design decision, unchanged in status from ADR-212/218.*
- **Tier-3 confirmation of ADR-219's three rows** — not dispatched this
  session for the reason above; needed before these numbers are cited outside
  this log. *2nd-order — a confirmation obligation on this session's own
  rows, not new scope.*
- **`test_the_r_probe_runs_end_to_end` is green only when
  `OPENBLAS_NUM_THREADS` is pinned** — discovered while running this session's
  baseline, quantified above (fails at the 4-thread container default,
  passes at 1, both on unmodified `main`), and **NOT fixed here: it is outside
  slice 7c's scope and touching a committed conformance test to make a red
  local run green is exactly the kind of change that needs its own slice and
  its own justification.** The test asserts `converged` on a fit ADR-211/213
  already measured as thread-sensitive, so the candidate fixes (pin threads in
  the test, drop the `converged` assertion, or use `multistart=True` there)
  are not equivalent and the choice is a real decision. *1st-order — a defect
  in an originally-planned component, in committed code, filed the session it
  was found.*
