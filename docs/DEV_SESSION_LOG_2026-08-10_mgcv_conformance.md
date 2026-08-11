# Dev Session Log — 2026-08-10

## Item Selected

- **Source:** `docs/CONTINUATION_penalized_mi_surface.md` (IN PROGRESS, slices 1–4 done,
  slice 4's PR #190 **merged** 2026-08-09) → `docs/PLAN_penalized_mi_surface.md` slice 5
- **Priority:** ACTIVE EPIC (Tier-A, `COMMERCIAL_VIABILITY_REVIEW_2026-07-15`) — no
  fallback item taken
- **Title:** The `mgcv` conformance suite
- **Slice:** 5 of 7 — **PR #192**, with **PR #193** stacked on it (the run)
- **Branch:** `claude/quirky-ramanujan-ppo0sz` (environment-designated; the routine's
  `feat/auto-*` default is overridden per step 8)

## Baseline and end state

| | |
|---|---|
| Baseline (`main` @ `bae2ea3`) | **3129 passed, 3 skipped, 126 deselected** — no standing failures |
| End state (`make test`) | **3174 passed, 4 skipped, 126 deselected** (+46 tests; the +1 skip is the R-gated conformance test) |
| New module tests | 46 (45 pass here, 1 skips: no R in this container) |
| `tests/qa/` goldens | **94 passed, untouched** |
| perf row | `peak_mib` 33 (Δ+0), wall-time 1.007×, **no structural creep** (12 rows — first real verdict) |

The four SOA-conversion failures the routine's baseline note anticipates did **not**
occur — `scripts/convert_soa_tables.py` reached pymort and converted 6/6. The CIA 2014
tables are reported MISSING by the validator, as they are on every run.

## Ledger healing (step 4b)

One PR merged since the previous session log: **#190** (slice 4). Its PRODUCT_DIRECTION
entries were **already struck through with a SHIPPED footer** by the slice-4 session
itself (`PRODUCT_DIRECTION_2026-07-24.md`, "Appended 2026-08-09"). **No healing was
owed** — recorded because "nothing to do" and "not checked" look identical in a log that
omits the step.

## Decomposition Plan

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Penalized fitter core at fixed λ | ✅ Done | #187 (ADR-185) |
| 2 | REML λ selection + the Anchor-4 reporting fix | ✅ Done | #188 (ADR-186) |
| 3 | Bayesian bands + the first coverage study | ✅ Done | #189 (ADR-187) |
| 4 | Selector robustness + the unconditional interval | ✅ Done | #190 (ADR-188) |
| 5 | `mgcv` conformance suite | ✅ **Built and run** | **#192** + **#193** (ADR-189 + amd 1) |
| 6 | Harness integration and reporting | ⏳ Next | — |
| 7 | Real data against the registered predictions | 🔲 Planned (maintainer run) | — |

## Selection Rationale

Step 5 found `CONTINUATION_penalized_mi_surface.md` IN PROGRESS with slice 4 merged, so
the CONTINUATION *is* the work selection and steps 5b/6 are skipped. Slice 5 was marked
NEXT and explicitly unblocked by slice 4. No fallback item was considered, per the
ACTIVE EPIC guardrail.

## Verify Premise (step 7b)

The premise here is not a bug report but a claim about what is unverified, so it was
reproduced as such: `tr(F)`, the Kass-Steffey covariance and `gamma` are all present in
the shipped code with docstrings saying *adopted from mgcv and unverified* (PLAN Anchor
8), and `rscript_mgcv_available()` returns `False` in this container — there is no R here,
which is exactly why the slice's job is to build the artefacts rather than run them. Both
halves hold.

**One premise in the source material did NOT hold, and it changed the design.** PLAN slice
5 and ADR-188 both describe level 4 as "`vcov(m)` vs `vcov(m, unconditional = TRUE)`", read
as a matched-λ comparison. It cannot be: `mgcv` forms `Vc` **only when the smoothing
parameters were estimated**, so no fixed-`sp` fit produces one, and at free `sp` the two
implementations select different λ. Level 4 is therefore two metrics — the conditional `Vb`
at fixed λ (exact) plus an **inflation ratio** at independently-selected λ (weak, and
readable only after level 2 passes). Corrected in the plan, the ADR, the runbook and the
harvest rather than papered over, because ADR-188's failing gate depends on level 4 being
as sharp as it was described.

## What Was Done

**One R command is now the epic's only external dependency.** The suite ships our tensor
design *and* our difference penalties to `mgcv` via `paraPen`, so the model is identical on
both sides and every disagreement localises to arithmetic. That construction is ADR-151's,
extended: a PSD penalty added to a strictly concave Poisson log-likelihood is still
strictly concave, so the penalized MLE over a shared `(X, S_age, S_year)` is unique.

**The central correctness claim is verified without R**, which is the part that keeps this
slice honest rather than merely prepared. `penalized_score_infinity_norm` measures
`||Xᵀ(y - μ) - Sβ||∞` at the exported coefficients — the gradient of the penalized
log-likelihood — and the worst of the ten committed cells is **2.19e-10** on cells whose
deaths are O(1e2–1e3). So the exported coefficients *are* the unique penalized maximiser of
the exported problem, and any level-1 disagreement can only be R's solver or a convention.
A test pins the function against ADR-151's unpenalized version at `S = 0` (exact equality),
and another moves the coefficients off the optimum and requires the norm to rise — a
statistic near zero everywhere measures nothing.

**The workflow decision is that the mgcv output is a committed golden, not a live oracle.**
The expensive resource is the round trip, not the R compute, so the synthetic exchange
(640 KB, seed-pinned, byte-reproducible) *and* our own reference for it (90 KB) are
committed, and the implementer then iterates entirely offline. The guard that makes that
usable is the hash: both references record the exchange SHA-256 they were computed from,
and the comparator recomputes it from disk and refuses if either disagrees. HMD/ILEC are
unchanged — exchange local-only, report committed — and the exporter *refuses to default a
real-data output path into the repository*, because a licensing boundary crossed by
accident is crossed through a default.

**One measurement shaped the fixture.** The obvious way to keep the exchange small is a
coarser age grid; at a 2-year step both penalties saturate at the search bound `(1e8, 1e8)`
and `edf_total` lands on exactly **4.000** — the bilinear null space the two
second-difference penalties share. Level 2 would then compare a bounded grid against an
unbounded optimiser on a problem where the data identify neither λ. The age *range* is
narrowed instead, and a test now guards against the degeneracy returning. This is the
fourth time this epic has met that trap.

## Files Changed

| file | what |
|---|---|
| `src/polaris_re/analytics/experience_mgcv_conformance.py` | **new** — case matrix, exchange writer/reader + hash, Python reference, comparator, report renderer, `penalized_score_infinity_norm`, `rscript_mgcv_available` |
| `scripts/export_mgcv_case.py` | **new** — writes the exchange (TSV + JSON manifest) and the Python reference |
| `scripts/mgcv_conformance.R` | **new** — the R side; five levels over the case matrix, one reference JSON, exits non-zero on any R error |
| `scripts/compare_mgcv_conformance.py` | **new** — hash-guarded comparison, pass/fail table, committed report |
| `docs/RUNBOOK_mgcv_conformance.md` | **new** — the two commands, what each level means, the licensing line |
| `data/mgcv_exchange/synthetic/` | **new** — committed exchange (3 designs, 10 cells) + `python_reference.json` + `exchange.sha256` |
| `tests/test_analytics/test_experience_mgcv_conformance.py` | **new** — 46 tests |
| `Dockerfile`, `.dockerignore` | allowlist `data/mgcv_exchange/` (the runtime image runs the suite, and a test reads the committed exchange) |
| `docs/DECISIONS.md` | ADR-189 |
| `docs/PLAN_penalized_mi_surface.md` | slice 5 status + discharge note (BUILT, not RUN) |
| `docs/CONTINUATION_penalized_mi_surface.md` | status, slice list, "New in slice 5", open questions |
| `docs/PRODUCT_DIRECTION_2026-07-24.md` | slice-5 annotation on the standing BLOCKER + harvest |

## Tests Added

`tests/test_analytics/test_experience_mgcv_conformance.py` — 46, none requiring R:

- **The case matrix, asserted rather than trusted** — all five levels; three fixed-λ pairs
  including both saturated corners; the asymmetric `(1e3, 1e0)` scale-convention pair; two
  `k` pairs that move **both** margins (a pair moving one could hide a Kronecker
  column-ordering error); factor block present and absent; a `gamma` cell.
- **The exchange** — bit-exact round trip via `np.array_equal` (not a tolerance); the
  exported padded penalties equal what the fitter assembles, with exact zeros outside the
  tensor block; the hash moves on a 1e-12 nudge; a missing manifest is refused rather than
  hashed around; two exports are byte-identical.
- **The R-free guarantee** — every committed cell at the penalized maximiser; exact
  agreement with ADR-151's unpenalized score at `S = 0`; two-sided (the norm rises when
  coefficients are moved off the optimum).
- **The comparator, both directions** — known agreement passes; a **seeded disagreement per
  metric** fails *that named metric*; a null-space-crossing coefficient shift must break
  both level-1 metrics; refusals for a foreign hash, an exchange edited underneath,
  `scale_penalty` left on, a fixed cell fit at the wrong λ, a partial R run, and a
  different-width design.
- **Staleness guards on the committed golden** — re-hash; regenerate the exchange and
  compare; regenerate the *reference* and compare (**not** marked `@slow`: ~4 s measured,
  and a staleness guard excluded from `make test` fires the day after it was needed).
- **The R script by grep** — the three settings plus the guards around
  the one that could not be verified here. A file in another language is otherwise
  unreachable from Python tests, and ADR-186 amendment 2's lesson applies across languages.
- **The real-data path** — driven end to end on a synthetic frame put through
  `attach_empirical_base` exactly as the runbook's snippet does; the missing-`q_base`
  refusal names the step that adds it; the licensing refusals at the CLI boundary.

## Acceptance Criteria

| Criterion (PLAN slice 5) | Status | Notes |
|---|---|---|
| `scripts/export_mgcv_case.py` — TSV + JSON manifest, three cases, synthetic committed | ✅ | Real-data cases read a grouped-cells file; see ADR-189 decision 9 |
| `scripts/mgcv_conformance.R` — five levels, no arguments, non-zero on error | ✅ | `mgcv` + `jsonlite` only |
| `scripts/compare_mgcv_conformance.py` — hashes the exchange, pass/fail table, report | ✅ | Exit 2 on disagreement, 1 on inability to compare |
| `docs/RUNBOOK_mgcv_conformance.md` — the two commands | ✅ | Plus the level table and the licensing line |
| Exporter round-trips; comparator tolerances can fail; `mgcv_available()` gates the R path | ✅ | Bit-exact; seeded disagreement per metric; gate is a `Rscript` probe |
| Export a **matrix** (8–12 cells, saturated corners, two `k` pairs, ± factors) | ✅ | 10 cells, 3 designs, asserted by test |
| Dump intermediates, not just answers | ✅ | Coefficients, per-block edf, `sp`, both `vcov` variants, deviance, scale, iterations, rank |
| Pin the R environment in the output | ✅ | `sessionInfo()`, `packageVersion("mgcv")`, `jsonlite`, R version |
| CI never grows an R dependency | ✅ | Comparator is a script; the R test skips on `rscript_mgcv_available()` |
| **Levels 1–3 agree within stated tolerances, or the disagreement is recorded** | ❌ | **Requires the R run, which is the maintainer's.** Not achievable by this slice |
| **`tr(F)` moves from adopted to verified or refuted** | ❌ | Same — Anchor 8 stands |

**The last two are the honest status of this slice: BUILT, NOT RUN.** The criterion as
written did not distinguish building the suite from running it. Reporting it as discharged
would repeat the "stated **with the measurements**" failure PLAN slice 2 already recorded
once, so it is reported as what it is.

## Perf History

Row appended to `perf/history.jsonl` for the feature commit `b815968` — see the follow-up
commit `chore(perf): record perf/history.jsonl row for mgcv-conformance`. Exactly +1 line;
no existing row touched.

**Creep verdict: NO structural creep.** The log now holds **12 rows** against a window of 3,
so it has passed `2 × window` and the analyser is no longer returning `insufficient_data` —
this is the first routine PR to get a real verdict rather than a no-op. Project peak MiB
33 → 33 (Δ+0), wall-time recent/baseline **1.007×**, no config drift. Nothing to raise.

Worth stating because it will not be obvious next time: the row pins the *feature* commit,
not itself, and this slice touches no engine path — the exchange is built by the existing
fitter and read by nothing in the projection pipeline — so a flat row is the expected
result rather than a reassuring one.

## Open Questions / Follow-ups

1. **Will the R run happen, and when?** One command, no data, no arguments. It is now the
   epic's only external dependency and it gates both the Anchor-8 conversion of three
   quantities and the diagnosis of ADR-188's failing coverage gate.
2. **`scalePenalty`'s `paraPen` semantics are adopted, not verified** — no R here to check
   them. Guards are in place; a guard is not a verification. If `penalty_scaling`
   comes back non-trivial on the first run, that is the run's first finding.
3. **Two free-`sp` tolerances are provisional** — 0.5 decades on `log10 sp`, 1.0 on `edf`,
   reasoned from the grid and the shallow profile rather than measured. The answer is not to
   widen them to pass.
4. **Level 4 is structurally weaker than ADR-188 assumed** (see Verify Premise). Sharpening
   it costs either an analytic derivation or a second round trip at R's own selected `sp`.
5. **Should slice 6 wait for the run?** The plan put 6 behind 5 so the numbers reaching a
   human would be verified first; they are not yet. A maintainer decision.

All five are promoted to `PRODUCT_DIRECTION_2026-07-24.md` under "Harvested 2026-08-10"
(items 2–5 as first-class entries; item 1 as an annotation on the standing BLOCKER rather
than a duplicate of it).

## Parked Polish

**None.** Every follow-up this session produced is first-order — a follow-up of slice 5,
which is an originally-planned feature of the epic. Nothing reached second order, let alone
the third-order cap.

## Impact on Golden Baselines

**None.** `tests/qa/` 94 passed unmodified, and the `polaris price` spot-check on
`golden_config_flat.json` is unchanged. Nothing in `products/`, `reinsurance/`,
`assumptions/` or the CLI was touched — the epic's byte-identical-goldens discipline holds
through slice 5. `data/mgcv_exchange/` is a new committed directory but no golden reads it;
it is read only by the new module's own staleness guards.

---

## Postscript — the run happened the same day (PR #193)

Written after the fact, appended rather than edited into the body above, because the
sequence is the record: this log said **BUILT, NOT RUN** and named the R run as the thing
that would settle Anchor 8. It was settled hours later.

`.github/workflows/mgcv-conformance.yml` (PR #193, stacked on this branch) runs the suite in
CI against the committed synthetic exchange in a digest-pinned container — R 4.6.1 /
mgcv 1.9.4 / jsonlite 2.0.0, CRAN snapshot 2026-08-01. **Nobody needs R installed**, which
makes the "two to three round trips" estimate in this log's plan section obsolete in the best
way. ADR-151 / Anchor 5 still hold: no job runs pytest and the trigger is path-filtered.

```
level 1: AGREES     level 2: AGREES     level 3: AGREES
level 4: DISAGREES  level 5: DISAGREES
```

**Both ❌ acceptance rows in the table above are now ✅.** Levels 1–3 agree — worst
`max_abs_coef_diff` 4.9971e-13 against a 1e-6 tolerance, `abs_edf_total_diff` 7.2120e-13
against 1e-6 — so `tr(F)` is **verified**, and the "or the disagreement is recorded" branch
was not needed.

**Decision 2's prediction held exactly.** The R-free guarantee said any level-1 disagreement
could only be R's solver or a convention, because `||Xᵀ(y − μ) − Sβ||∞` measured 2.19e-10.
There is no level-1 disagreement. That is the strongest confirmation available that the
correct-by-construction argument was sound rather than merely plausible.

### What this log got wrong

Three things, and they are worth more than the things it got right.

1. **`scalePenalty` is not load-bearing.** This log called it "the one setting that is
   load-bearing" and described four defences around it. It never reaches `paraPen`:
   structurally `gam.setup` passes `scale.penalty` only into `smoothCon()`; empirically, with
   penalties mismatched by `1e6` at fixed λ, `max|coef(TRUE) − coef(FALSE)|` is **exactly 0**.
   The guarantee was structural all along.
2. **`penalty_scaling()` was never a live defence, and it cried wolf.** It could only ever
   return `full.sp` — the smoothing-parameter vector, not a rescaling factor — and it fired
   the "sp did not multiply the supplied S" note on **all ten cells** of a run where level 1
   agreed to 1e-13. **Two defects of opposite polarity on the same setting in two rounds**
   (round 1: a guard that could fail silently; round 2: a guard that fires always). Both came
   from believing it load-bearing. Over-engineering a hazard that does not exist produces its
   own defects.
3. **The suite had never executed, and "BUILT" concealed that.** Every fixed-λ cell crashed —
   λ went through `gam()`'s top-level `sp`, which a `paraPen`-only fit cannot accept
   (`gam.setup` dies at `fix.ind <- G$sp >= 0`). Six of ten cells. The R side's coverage was a
   **grep test over a file the suite cannot execute**, and this log listed that test as
   covering "the R script". The R-gated end-to-end test would have caught it and skipped
   everywhere. **CI closed the gap, not an assertion** — and that generalises: for an artefact
   in a language the test suite cannot run, the only real coverage is an environment that runs
   it.

### The finding that matters

**Level 4 refutes the Kass-Steffey covariance: it systematically under-inflates.** Ours
1.11–1.21×, mgcv 1.49–1.87×, every cell the same direction, two of three past the 0.25
tolerance. This is the discrimination slice 5 was sequenced for — ADR-188's Anchor-7 gate
failed at 0.8516 / 0.8581 against a 0.9192 floor with two candidate causes, and level 4 points
at **our arithmetic** rather than shrinkage bias. An under-inflated covariance under-covers, in
the observed direction, on the same cells. Promoted as a **BLOCKER** with the three places to
look.

And the worry recorded in this log's Verify Premise section — that level 4 was weakened to an
inflation ratio and might not discriminate — was **half right**: it is weak, and it was still
enough, because a three-cell same-direction 1.5×-sized miss is not what λ disagreement
produces, and level 2 passes.

### Level 5, and the tolerances

`gamma` is **unsettled, not refuted**: both PROVISIONAL tolerances miss narrowly (6.7244e-01
vs 0.5; 1.1270 vs 1.0) while the cross-cell sign check passes. The same two metrics at
`gamma = 1.0` **pass** narrowly (4.3221e-01, 8.7334e-01) — ~13% of headroom each. **No
tolerance was widened**, per this log's own advance commitment and the maintainer's restatement
of it on #192.

## Impact on Golden Baselines — unchanged

Still none. The postscript work is documentation plus three comment/rationale corrections in
`experience_mgcv_conformance.py`; no behaviour moved and `tests/qa/` is untouched.
