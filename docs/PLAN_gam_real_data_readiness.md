# Plan: make the GAM fitter ready for real data — factor-by with `select=TRUE`, the ILEC trial, scale, and `tp`

> **STATUS: PROPOSED 2026-10-10, revised after the maintainer's PR review the same day (ADR-257) — becomes the ACTIVE EPIC when the PR that adds it merges.** Execution order (maintainer): **R1, then R2, then R4; R3 only if the time ceiling is unmet** (slice labels are not renumbered). The preview epic (`PLAN_gam_parity_preview.md`) is DONE and parity-engine Slice 10 is DONE as a finding (ADR-256). Nothing in those files changes.

**Source:** maintainer direction, 2026-10-10: *"we now have a working HGAM fitter … fitting against [real ILEC data] … perf will likely need our attention … `bam` and `discrete=TRUE` will be obvious features to develop … the fitter [must be] performant on real data before we expose and wire this into pricing"*; factor-by with `select=TRUE` is required **before** moving to real data; `tp` (for bare `s(x)`) outranks `sz`; the maintainer has local Docker, the ILEC data and Claude Cowork on one machine.
**Predecessors:** `PLAN_gam_parity_preview.md` (the verified subset and the public `gam()` entry point), `PLAN_mgcv_parity_engine.md` (engine, ADR-256 for the rank-deficiency finding), `PLAN_mgcv_capability_ladder.md` (rungs; L7 = `tp`, L9/L10 = `fREML`/`bam`), `MGCV_FEATURE_COVERAGE.md`.
**Routine:** `ROUTINE_MGCV_PARITY.md` — same tiers, provenance gate and nevers, plus the **maintainer-run step protocol** in §3 (new).
**Total slices:** 4. **No slice may be split without maintainer approval** (§5).

---

## 1. Where we stand (measured, not assumed)

| question | answer today | evidence |
|---|---|---|
| Does a verified HGAM fitter exist? | yes, for the verified subset: `cr` (plain, numeric-`by`, factor-`by`), `ti`, `re`, parametric, `select=TRUE` on those; gaussian / poisson / quasipoisson / binomial; deterministic Newton REML; `predict`, `se.fit`, `summary()` | `GAM_USER_GUIDE.md` §5, `GAM_PARITY_REPORT.md` (tier 3, run 38017135360) |
| Has it seen real data? | **no.** All parity cells are synthetic; the largest is 5,000 rows, 15 penalties | report §3 |
| Is `select=TRUE` with a factor-`by` smooth available? | **refused by name** ("the free-`sp` search is not verified on that block shape") | guide §6 |
| What does a redundant coefficient cost? | per-term edf and `Vc` of a *pivoted* fit are not identified, and `mgcv` itself does not reproduce them (15 of 24 draws differ across `OPENBLAS_NUM_THREADS`); the fit warns (`PolarisRankDeficiencyWarning`) | ADR-256 |
| Is a bare `s(x)` expressible? | no (mgcv's default is `tp`, rung L7) | guide §6 |
| What would real data look like? | SOA-ILEC 2012-2019: 11,059,501 rows after filtering, 126,223 grouped cells (banded run) on the keys age, year, duration, sex, smoker, plan, face band, preferred class; `Policies_Exposed` / `Death_Count` measures | `MEASUREMENT_experience_gam_ilec.md` (cell-count table), `experience_loaders.ILEC_2012_19_COLUMN_MAP` |
| Where does time go at scale? | **unknown.** No profile exists beyond one 5,000-row cell and the older engine's measurements. This plan exists to find out | — |

## 2. The definition of done (the epic's acceptance test)

A maintainer with the ILEC file on their machine can, with one runbook and no code changes:

1. fit each trial formula (§4, Slice R2) through `polaris_re.gam.gam(...)` on ILEC-derived cells within the **time ceiling** (§6: 10 minutes, Polaris fit only, on the fixed reference machine) and with the Polaris/`mgcv::gam` wall-time ratio **reported** against the same cells on the same machine (a ratio above **1.5** at `full` granularity triggers the `bam` investigation of Slice R3; it is a trigger, not an agreement gate);
2. see **agreement with `mgcv`** on the existing gates (`eta` < 2e-2, |`edf_total` diff| < 1, `Vp` `se` < 2e-2; ADR-221/250) **and** the scale-aware criterion below, reported per formula, plus timing and size, in a **derived-scalars-only** file;
3. fit factor-`by` smooths with `select=TRUE` and with the bare-main-smooth form without a surprise (§4, Slice R1);
4. write a bare `s(x)` and have it accepted as `tp` (§4, Slice R4);

and nothing outside the verified subset is accepted silently (refusals by name stay).

**Why a scale-aware criterion as well (maintainer review, 2026-10-10).** ADR-221's absolute gates were set on 5,000-row synthetic cells. At ~10^5 cells the fit's sampling uncertainty is far smaller, so an absolute 2e-2 on the link scale can pass a difference that is large relative to what the data can resolve. Fixed **before** the first run: every trial cell must also satisfy **max |eta_Polaris - eta_mgcv| / se.fit_mgcv <= 0.1** (a numerical disagreement must be small against the fit's own standard error; `se.fit` under `Vp`). Both the ADR-221 gates (imported, unchanged) and this ratio must hold; neither is relaxed to pass the other. The 0.1 value is a recommendation awaiting the maintainer's confirmation (Q-R2e) and, once confirmed, is not changed after R2 runs.

**Explicitly not in this epic:** wiring the fitter into pricing, the CLI, dashboard or MCP (Anchor 7 stays; a maintainer decision *after* R2/R3); `sz` free-`sp` (parked, maintainer 2026-10-10); `te`/`t2`/`fs`; p-values.

## 3. How real-data steps run (new protocol — ADR-257)

The scheduled routine runs in a cloud sandbox with **no access to the ILEC file** and must not have it (`DATA_LICENSING.md`, Design Anchor 6). Real-data slices therefore have two halves:

- **Routine half (cloud):** code, tests on synthetic fixtures, a runbook, an R companion script, the pre-registered predictions and the output schema. It ends the session with the slice marked **WAITING ON MAINTAINER RUN** — a legitimate stop condition, not a failure and not a reason to start the next slice early.
- **Maintainer half (local, Docker + Cowork):** Cowork follows `docs/RUNBOOK_gam_real_data_trial.md` (written in R2) end to end on the maintainer's machine and writes **one JSON file of derived scalars**. The maintainer reviews it and either commits it (`docs/measurements/`, per `DATA_LICENSING.md` §5 and the position in §5a) or pastes it to the next session. The slice is **DONE when the result is recorded**, whatever it says.

**Evidence tier for those runs: tier L ("pinned image, run locally on the maintainer's machine").** It uses the *same image digest* as tier 3 (`ORACLE_IMAGE` in `mgcv-conformance.yml`), so it is the routine's own "tier 2", currently unavailable in the cloud. Rules: every number carries the digest, `OPENBLAS_NUM_THREADS` and the Polaris commit; a tier-L number may appear where tier 3 may (ADR, ledger, CONTINUATION) **only** if labelled "tier L, real data, maintainer-run"; it never replaces a tier-3 number for a synthetic cell; wall-clock times are machine-dependent and are labelled with the machine's description, never compared across machines.

**The derived-scalars-only contract.** The trial script writes only: sizes (rows, cells, columns, penalties), timings per phase, iteration counts, peak memory, `edf` (total and per term), `log10(sp)`, REML score, scale, convergence flags, and the *differences* from `mgcv` (`eta` max/rms, `edf_total`, `se`). It writes **no** row, cell key, level name, factor level count, exposure, death count, rate, A/E, fitted curve, **or any model coefficient or contrast** (for example the smoker S-vs-NS effect: its size stays on the maintainer's machine). Row and cell counts of the banded run are already committed in `MEASUREMENT_experience_gam_ilec.md`; cell counts at the other granularities are new *sizes* and are covered by the Q-R2c "yes" (timings, sizes, agreement differences only). A test on a synthetic fixture asserts the output keys against a whitelist and fails on any other key, so the contract is enforced, not promised.

## 4. The slices

Every slice lands **(i) one user-callable capability and (ii) at least one INDEPENDENT comparison of it** (tier 3, or tier L for R2). A slice that can land only harness work is reported as blocked (§5), not re-scoped.

### Slice R1 — `select=TRUE` with factor-`by` smooths (and the bare-main-smooth form)

**Why first (maintainer).** The real model formulas need it, and it may remove a limitation: ADR-255 observed that `select=TRUE`'s null-space penalties would identify the direction `s(x) + s(x, by=f)` leaves unidentified. If so, such a fit has **no pivot**, so per-term edf and `Vc` are well defined — and, if `mgcv` is stable there, gateable under the strict definition.

**Claim sentence (ADR-193), written before the code.** *Polaris (`gam()` → `fit_polaris_gam`) fits `select=TRUE` with a factor-`by` smooth from the formula string and the data columns (assembly, null-space penalty per level, Newton free-`sp`); `mgcv` fits `gam(<same string>, method="REML", select=TRUE)`; compared on `eta`, `edf_total`, the `Vp` and `Vc` `se`, per-smooth edf, term structure.* Signatures take no `mgcv` output (mechanical test unchanged).

**Scope.** (1) lift the guide §6 refusal for `select=TRUE` + factor-`by`; (2) forms `f + s(x, by=f, bs="cr")` and `s(x, bs="cr") + s(x, by=f, bs="cr")`, each with/without `f`; (3) families gaussian, poisson, quasipoisson, binomial; (4) extend `scripts/gam_pivot_stability_probe.R` to these cells so `mgcv`'s own run-to-run stability is measured **first**; (5) INDEPENDENT tier-3 cells added to the existing predict, formula and summary sections.

**Pre-registered predictions (tier 1 hypotheses until tier 3):**
- **R1-a:** with `select=TRUE`, `unidentified_directions` is empty for `s(x) + s(x, by=f)` — no pivot, no warning. *If false:* the form stays a pivoted fit under ADR-256's rules (warning, per-term edf reported not gated).
- **R1-b:** `mgcv`'s eliminated/penalised structure is thread-stable on these cells (the probe, tier 3). *If true:* per-term edf and `Vc` are gated under ADR-253 / ADR-250 on the unpivoted cells. *If false:* ADR-256 applies unchanged.
- **R1-c:** `eta` and `edf_total` agree inside ADR-221; `log10(sp)` differs on plateau blocks and is reported, never gated.
- **R1-d:** the free-`sp` search may fail to converge on some per-level null-space blocks (the original reason for the refusal). *Handling is fixed in advance:* record the cell as a limitation and **keep refusing that construct by name** (§5 rule 3); no start strategy, no solver tuning.

**Acceptance (INDEPENDENT, tier 3, existing gates, none widened):** every form × family cell meets `eta` < 2e-2, |`edf_total`| < 1, `Vp` `se` < 2e-2, converges from one Newton start; per-term edf and `Vc` `se` are gated **only** on cells where R1-a and R1-b hold, and reported otherwise. **Release condition:** first slice; no precondition.

### Slice R2 — the ILEC trial and the performance profile (WAITING ON MAINTAINER RUN)

**What the routine builds.** `scripts/gam_real_data_trial.py` (loads ILEC via `experience_loaders.load_ilec`, aggregates to the trial cells, fits with `gam()`, times each phase, calls the R companion), `scripts/gam_real_data_trial.R` (the same formula string under the pinned `mgcv`), `docs/RUNBOOK_gam_real_data_trial.md` (written so Cowork can execute it without judgement calls: environment variables, the Docker command with the digest, expected runtime, the exact output path, a checklist of "stop and report" conditions), and the output whitelist test (§3).

**Trial formulas (maintainer-approved with changes, 2026-10-10).** Explicit `bs="cr"`; family **Poisson(log) with `offset(log(exposure))`** where `exposure` is `Policies_Exposed` (fractional, so a binomial trial count only approximately — maintainer review); `smoker` has **three levels `NS`/`S`/`U`** (loader canonical labels; the file's codes are `NS`/`S`/`U`, not the dictionary's `N`) and **`U` is kept as its own level** in every main fit (it is not a blend of NS and S, its share is stable across 2012-2019, and excluding it drops a large part of the data).
- **T1 (smooth only):** `s(attained_age, k=13) + s(duration, k=6) + ti(attained_age, duration, k=c(13,6))`.
- **T2 (+ parametric block, the target's own shape):** T1 + `face_band + smoker + face_band:smoker`.
- **T3 (+ factor-`by`, `select=TRUE`):** T2 + `s(attained_age, by=smoker)` (R1's capability).
- **Sensitivities (each one fit, reported as agreement/timing only):** **S1** the target's own family on T2: `binomial(cloglog)` with the proportion response and `weights = exposure` (the parity plan's `bam(..., family = binomial(link = "cloglog"), weights = ExposCnt)`), labelled an approximation when exposure is fractional; **S2** T3 with `U` dropped (agreement on both fits is whitelist; the S-vs-NS contrast itself is **not** committed, per §3); **S3** T3 plus a cohort term (`issue_year = calendar_year - duration + 1`, derived from mapped columns, no loader change), to separate `U` from issue cohort.
Each at **three aggregation granularities**: **coarse** (age x calendar year), **mid** (+ duration, sex, smoker), **full = exactly the key set of the committed banded run** (`MEASUREMENT_experience_gam_ilec.md`), so the profile is comparable with committed numbers. Collapsing rows to cells is lossless for Poisson counts with an exposure offset, so a cell fit is the same model as the row fit.

**Data rules the runbook pins and the script asserts (from the maintainer's data review).** `Duration` is a 1-based policy year and `Attained_Age = Issue_Age + Duration - 1` holds across the file (assert it; it matches the loader's `(d-1)*12`); `Age_Ind` is coded `ANB`/`ALB` and the loader ignores it (no code change); zero-exposure rows are dropped **after asserting zero deaths on them**; `ExpDth_VBT2015_Cnt` is populated so `include_expected` gives SOA's independent A/E check if wanted (not required by this epic); and **before using the full 2012-2019 window** the run checks whether the 2018-2019 composition change reflects a new submitting company — a stop-and-report condition whose numbers stay local (the maintainer then picks the window). The runbook also records the corrected dictionary note: `U` is not confined to issue years before 1981.

**Time and machine.** Ceiling **10 minutes, a ceiling and not a target, applying to the Polaris fit only** (not the `mgcv` oracle, which may take far longer). The reference figure of about 10 minutes for about 10M rows came from `mgcv::bam`, which this repository does not implement, so it is not an oracle time for `gam`. The comparison is `mgcv::gam` on the same banded cells on the same machine; the Polaris/`mgcv::gam` wall-time ratio is **reported** for every formula and granularity, and **a ratio above 1.5 on any main-fit formula (T1-T3) at `full` granularity requires investigating `bam`** (maintainer, 2026-10-10: Q-R2b2). The ratio is a trigger for R3, not a pass/fail gate on agreement; sensitivities S1-S3 and the coarse/mid granularities are reported, not triggering (the `full`-granularity reading is my reading of the maintainer's wording, confirmed or corrected on the PR). The **reference machine is fixed by the first R2 run**: the runbook records its description (CPU model, cores, RAM, OS, Docker limits, `OPENBLAS_NUM_THREADS`) in the result file, and a result from any other machine is labelled non-comparable for the budget.

**The question the profile answers.** For each formula/granularity: wall time split into design assembly, IRLS/PIRLS, REML gradient/Hessian, outer iterations; peak memory; iterations; how time grows with cells (n) and coefficients (p). The decision it feeds is R3's.

**Claim sentence.** *Polaris (`gam()`) fits the formula from the ILEC-derived columns; `mgcv` (pinned digest, `gam(method="REML")`) fits the same string on the same columns; compared on `eta`, `edf_total`, `Vp` `se`, per-term edf, `log10(sp)`, REML score.* INDEPENDENT; tier L. Real-data disagreements are results: they are recorded, the construct is refused or flagged, and the epic moves on (§5 rule 3).

**Acceptance.** For each formula/granularity, either the existing gates **and the scale-aware criterion** are met or the disagreement is characterised with a named mechanism class (ADR-241 rule: basis / criterion / outer search / other); timings and sizes recorded; the profile table committed as derived scalars (subject to Q-R2c). **Release condition:** R1 DONE (T3 needs it); the routine half can start as soon as R1's code is merged.

### Slice R3 — scale: exact speedups, or `bam` with `discrete=TRUE`

**Decided by R2's profile, not before.** Maintainer reserved scope decision (`ROUTINE_MGCV_PARITY.md`, "may not decide") is recorded here as: *`bam`/`fREML`/`discrete=TRUE` ENTER scope conditionally — if and only if R2 shows exact speedups cannot meet the time budget.* The two branches:
- **R3-exact:** speedups that leave every output unchanged to rounding (collapse rows to unique covariate cells with exposure as weights; blocked/streamed `X'WX`; avoiding dense `n × p` temporaries). Verified by a bit-tolerance equivalence test against the current path **and** unchanged tier-3 cells. No new oracle.
- **R3-bam:** `fREML` + discretised covariates as a **new algorithm** (ladder L9/L10; Wood/Li/Shaddick/Augustin). The oracle becomes `bam(discrete=TRUE)`; the claim sentence, gates and what "agree" means are **derived in the slice's ADR before code** (a different criterion is not a faster REML). Earlier measurement for context: `bam` vs `gam` at fixed `sp` on a `paraPen`-only model agrees to 2.1e-12, and `bam` at 125,000 rows took 1.69 s (PLAN-parity, deferral note).
- **Release condition:** R2 recorded and either the 10-minute ceiling is exceeded or the Polaris/`mgcv::gam` ratio is above 1.5 (main-fit formulas, `full` granularity). "Investigating `bam`" means R3 opens with R2's profile deciding between R3-exact and R3-bam; it does not pre-commit to building `bam`. Executes **after R4** (maintainer order). If the budget is met, R3 is closed as "not needed" with the profile as evidence — a success.

### Slice R4 — `tp` (ladder L7) so a bare `s(x)` is accepted

Independent of R2/R3; executes **second after R2** (maintainer order: R1, R2, R4, then R3 only if needed). **Claim sentence:** *Polaris builds the thin-plate regression spline design and penalty from the covariate and `k`; `mgcv` builds `smoothCon(s(x, bs="tp", k=))`; Stage A compared on `X` and `S` (exact), Stage B on `eta`/`edf`.* Then: a bare `s(x)` is parsed as `tp` (ADR-248 decision 2), the guide §6 row becomes a supported row, and tier-3 cells are added. Known cost: the eigen-decomposition of the thin-plate penalty (ladder estimate medium-large); `mgcv`'s default `tp` truncation is the usual trap — Stage A first. **Release condition:** after R1; no real-data dependency.

## 5. Rules that keep this epic from spiralling

1. **Every slice ships a capability** plus one INDEPENDENT comparison; harness-only work is a sub-step, never a slice. The routine half of R2 counts because it ships the runnable trial and the whitelist-tested output, and R2 is DONE only when a real result is recorded.
2. **No splitting, no letter-suffix slices** without a maintainer comment. A slice that cannot finish opens as WIP; the next session finishes the same scope.
3. **A disagreement is a limitation first, a slice never.** Outside the target formula it is recorded in the guide's limitations and the refusal list; only a disagreement *on a trial formula* blocks, and its mechanism goes to the owning plan (outer search → `PLAN_wood_outer_solver.md`'s gauntlet, never a new start strategy).
4. **No solver work.** No start strategy, multistart, or tuning. A solver-shaped gap is a recorded limitation or Slice 3b's registered release condition.
5. **Real data never enters the repo or the cloud** (§3). A session asked to "just look at the data" says no and points at the runbook.
6. **R3 is gated on R2's measurement.** The routine does not pick `bam` because it is the named feature in the objective.
7. **Questions go to the maintainer the session they arise** (PR body + CONTINUATION "Maintainer questions", with a recommended answer). Work that does not depend on the answer continues.

## 6. Maintainer answers (PR review, 2026-10-10) and what is still open

**Answered:** **Q-R2a** T1-T3 accepted with the changes in R2 (three smoker levels, `U` kept; Poisson with offset as the primary family; `binomial(cloglog)` as sensitivity S1; units pinned in the runbook). **Q-R2b** ceiling 10 minutes on the Polaris fit only, fixed reference machine; **Q-R2b2** report the Polaris/`mgcv::gam` ratio and a ratio above **1.5** requires investigating `bam` (answered 2026-10-10). **Q-R2c** yes for timings, sizes and agreement differences; row and cell counts of the banded run are already public; level counts are dropped from the whitelist; contrasts and coefficients are excluded. **Q-R2d** accepted, with `full` = the banded run's key set. **Q-order** R1, R2, R4; R3 only if the ceiling is exceeded or the wall-time ratio is above 1.5.

**Still open (recommended answers):**
- **Q-R2b2 confirmation (one line).** The 1.5 trigger applies to T1-T3 at `full` granularity only. *Recommended:* yes; a ratio above 1.5 only at a sensitivity or smaller granularity is reported and noted, not a trigger.
- **Q-R2e — the scale-aware agreement criterion.** `max |Δeta| / se.fit <= 0.1` (DoD). *Recommended:* accept 0.1 (numerical error an order of magnitude below statistical error); fixed before R2 runs.
- **Q-R2f — reference machine.** Is the maintainer's current machine the reference? *Recommended:* yes; the first R2 result file records its description and later results from other machines are labelled non-comparable.

## 7. Risks, in the order they are likely to bite

1. **`select=TRUE` + factor-`by` plateaus** (per-level null-space blocks, large `sp` spreads): the original reason for the refusal. Pre-registered handling in R1-d.
2. **Dense linear algebra at 100k+ cells.** Unmeasured; R2 measures it. The older engine fitted 125,676 cells, but with a different (tensor P-spline) construction.
3. **The oracle's wall time.** `mgcv::gam` on the same cells may itself take minutes-to-hours; the runbook records its time too and the trial must be restartable per formula.
4. **Cowork-run reproducibility.** The runbook pins the digest, thread count and commit; a result without all three is rejected by the next session.
5. **Licensing drift.** Any new kind of number from ILEC (anything beyond §3's list) needs Q-R2c's answer extended first.
