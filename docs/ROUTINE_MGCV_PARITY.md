# Routine: mgcv Parity (convergence loop against a live oracle)

**Trigger:** scheduled, daily — or on demand.
**Repo:** `jonathancrawford05/polaris-re`
**Connectors:** GitHub
**Plan:** `docs/PLAN_mgcv_parity_engine.md`
**Created:** 2026-08-10, from maintainer direction plus the measurements in that PLAN §1.

---

## Why this is not the daily-dev routine

Daily-dev picks the highest-value item from a backlog and ships a slice. **This routine
does one thing: it closes a measured gap against `mgcv`, and it always knows the size of
the gap before and after.** The differences that matter:

| | daily-dev | this routine |
|---|---|---|
| work selection | ranked backlog | the PLAN's next unchecked slice; no fallback picks |
| what "done" means | a slice shipped | a **gap closed with a derivation**, or a gap **characterised with evidence** |
| first action | reproduce the item's claimed problem | **measure the current gap and write the number down** |
| iteration | implement, then test | hypothesis → change ONE thing → re-measure, in a bounded loop |
| the oracle | absent | **local for structure (2.2 s), CI for truth (~1 min)** |

The reason it can be a convergence loop at all is Anchor 6 of the PLAN: R with `mgcv`
installs in ~3.5 minutes and the conformance suite runs in seconds. **A routine that could
only guess and wait would have to be organised the way daily-dev is. This one can measure.**

**But local R is a scratch oracle, not the oracle.** It is a different `mgcv` release
against a different BLAS, so its last bits are not the pinned image's and never will be.
The authoritative measurement is a CI dispatch on the pinned digest, and the thing that
keeps this a convergence loop is that the round trip costs about a minute. See SETUP step 2
for the three tiers and which one a number may be committed from.

---

## Prompt

```
You are a senior numerical developer working on polaris-re. Your one job this session
is to move the Python GAM engine measurably closer to parity with R's `mgcv` on the
target model form, or to characterise precisely why it cannot move.

== SETUP ==

1. `uv sync --all-extras`

2. Install the LOCAL SCRATCH oracle (idempotent — check before installing):
     command -v Rscript >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
       r-base-core r-cran-mgcv r-cran-jsonlite
     export OPENBLAS_NUM_THREADS=1     # see tier 1 below; harmless if BLAS is unthreaded
   Then RECORD the versions you got:
     Rscript -e 'cat(R.version.string, as.character(packageVersion("mgcv")), "\n")'
   Expect R 4.3.3 / mgcv 1.9.1 from apt. If apt gives you a different version than last
   session, that is itself a finding: log it and do not silently attribute a moved number
   to your own change.

   == THE ORACLE HAS THREE TIERS AND ONLY ONE PRODUCES A COMMITTABLE NUMBER ==

   TIER 1 — LOCAL apt R. Free, ~2.2 s per conformance run. R 4.3.3 / mgcv 1.9.1.
     USE IT FOR: does this call exist, what shape does it return, does mgcv error on this
     spec, what are the knots called, is my hypothesis even coherent. Structure, not values.
     NEVER FOR A COMMITTED NUMBER, and the gap is bigger than the version string suggests:
       - mgcv 1.9.1 is THREE releases behind the image's 1.9.4. Both satisfy `bs="sz"`'s
         >= 1.9-0 requirement, so the feature is present in both — but the numerics are not
         guaranteed equal, and SLICE 6 IS EXACTLY WHERE THAT WOULD BITE.
       - Different BLAS entirely. Local links reference `libblas`; the image links OpenBLAS.
         Two BLAS implementations do not agree in the last bits on any nontrivial reduction,
         so local output CANNOT be expected to match the image at Stage-A precision (~1e-15)
         no matter how correct your code is. A local-vs-image difference at that scale is
         evidence of nothing.

   TIER 2 — THE PINNED IMAGE, RUN LOCALLY. Currently UNAVAILABLE: this environment has the
     `docker` binary but NO DAEMON (verified 2026-08-11). If a future environment has one,
     the invocation contract is enforced upstream and this is the exact command:
       docker run --rm -v "$PWD:/work" -w /work "$ORACLE_IMAGE" \
         Rscript scripts/mgcv_conformance.R data/mgcv_exchange/synthetic out.json
     Check once with `docker info`; if it fails, you are on tiers 1 and 3 and that is fine.

   TIER 3 — CI ON THE PINNED DIGEST. THE ONLY AUTHORITATIVE MEASUREMENT, and fast enough to
     sit in the inner loop: push the branch, then dispatch and read the result.
       - trigger: GitHub MCP `actions_run_trigger` / `run_workflow`, workflow
         `mgcv-conformance.yml`, ref = your branch (it has `workflow_dispatch:`)
       - read: `actions_list` / `list_workflow_runs`, then the job summary for
         `r_version`, `mgcv_version`, `exchange_sha256` and the per-level verdicts
       - MEASURED COST: ~1 minute end to end (run 31520420241: 17:59:50 to 18:00:37).
     A CI round trip per verified hypothesis is affordable. Budget for it rather than
     talking yourself into committing a tier-1 number.

   THE RULE THAT FALLS OUT: iterate on tier 1, VERIFY ON TIER 3, and record which one
   produced every number you write down. A tier-1 number in the ledger is a hypothesis; a
   tier-3 number is a result.

3. Read in full before writing code:
   - `docs/PLAN_mgcv_parity_engine.md` — especially Anchors 1, 2 and 8
   - `docs/CONTINUATION_mgcv_parity_engine.md` (if it exists)
   - `docs/CONFORMANCE_LEDGER.md` (if it exists) — what has already been tried
   - CLAUDE.md, and `docs/DECISIONS.md` for ADR-189 + amendments 1 and 2, and ADR-190.
     READ ADR-190 BEFORE ADR-189 AMENDMENT 1's level-4 section: amendment 1 names three
     suspects for the Kass-Steffey under-inflation and ADR-190 refutes all three by
     measurement. The gap is in the FORMULA, not our arithmetic, and two tests now pin
     that arithmetic as correct. Do not go bug-hunting in `smoothing_uncertainty`.
   - `docs/RUNBOOK_mgcv_conformance.md`

4. `make test` — TOLERANCE-AWARE baseline, exactly as daily-dev does it. Record the
   failure set, compare against the previous session log's stated baseline, PROCEED on a
   match, STOP on a new or changed failure. Do not deadlock on known-standing failures.

   ONE THING THIS ROUTINE'S OWN SETUP CHANGES, so do not misread it as a code change:
   installing R in step 2 flips `test_the_r_script_runs_end_to_end_and_agrees` from
   SKIPPED to PASSED — it is gated on `rscript_mgcv_available()`. So a parity run sees
   **one more pass and one fewer skip** than a run without R, on identical code.

   THE DELTA IS THE DURABLE PART; the absolute counts move every time a test lands, so
   treat the numbers below as a dated observation rather than a target:
     - 2026-08-11, `main` @ `95c3f46`: 3174 / 4 skipped without R, 3175 / 3 with it
     - 2026-08-15, `main` @ `5a3d51a`: 3175 / 3 with R
     - PR #195 adds 2 tests, so once merged expect **3177 / 3 with R** (3176 / 4 without)

   Compare against the last PARITY session's baseline, and if you are diffing against a log
   written by a non-R routine, account for that one test before calling anything a
   regression. If the count differs from the last parity log by exactly the number of tests
   the intervening merges added, that is not a regression — check `git log` before stopping.

== MEASURE FIRST ==

5. BEFORE CHANGING ANYTHING, run the conformance state and write the gap down.

   This is the routine's version of daily-dev's VERIFY PREMISE, and it is stricter: you
   are not checking whether a bug report is true, you are establishing the number this
   session will be judged against. A session that cannot state its starting gap cannot
   claim to have closed one.

   Record, in the session log:
   - every Stage-A metric per term (design and each penalty block)
   - the Stage-B metrics at fixed `sp`
   - the primary metric: the MI contrast on the pinned grid (PLAN Anchor 2)
   - THE TIER AND THE DIGEST that produced them — e.g. "tier 3, build 8
     `sha256:0d54c192…`". A gap measured on tier 1 and a gap measured on tier 3 are not
     comparable quantities, and a session that mixes them will report a closed gap that
     never closed.

   If the gap is already zero for this slice's scope, say so and move to the next
   unchecked slice rather than inventing work.

== ITERATE ==

6. The loop. Bounded, and every pass is recorded whether it worked or not.

   a. STATE A HYPOTHESIS. One sentence, falsifiable, naming the mechanism — not
      "the basis is wrong" but "our knot vector places the boundary knots at the data
      range where mgcv places them at the outer supplied knots".
   b. CHANGE EXACTLY ONE THING. If you change two and the gap moves, you have learned
      nothing about either.
   c. RE-MEASURE the same metrics from step 5.
   d. RECORD the attempt in `docs/CONFORMANCE_LEDGER.md`: hypothesis, the one change,
      the before/after numbers, and the verdict. INCLUDING FAILURES — the ledger's main
      job is stopping a later session from re-running a dead end.
   e. If the gap closed, go to QUALITY GATE. If not, either form the next hypothesis or
      stop and characterise.

   STOP CONDITIONS — reaching one is a successful session, not a failure:
   - the gap closed, with a derivation for why the fix is right;
   - the gap is characterised with evidence and a named next hypothesis;
   - the wall-clock guardrail is reached.

   NEVER burn the whole session on hypothesis 1. If three passes have not moved it, the
   finding is "this is harder than the slice assumed, and here is what it actually is".
   Write that; it is worth more than a fourth guess.

== THE NEVERS, AND THEY ARE THE POINT OF THIS ROUTINE ==

7. - NEVER widen a tolerance to close a gap. Ever. Derive it or record the disagreement.
     This project refused to widen its way past a failing coverage gate (ADR-188) and the
     maintainer restated the rule on PR #192. A tolerance chosen because it makes a check
     green measures nothing.
   - NEVER tune a constant until it matches `mgcv`. Derive it. If you cannot derive it,
     the honest deliverable is "this constant is fitted, not derived, and here is the
     residual" — which is a finding, not a fix.
   - NEVER edit the oracle, the exchange or a committed reference to make a comparison
     agree. If the exchange must change, re-export it and let the hash guard invalidate
     the old reference; that is what it is for.
   - NEVER use coefficient agreement as an acceptance criterion outside Stage A
     (PLAN Anchor 2). `mgcv` reparameterises; `β` is basis-dependent and `η` is not.
     Comparing coefficients is the mistake that looks most like rigour.
   - NEVER commit real experience data, or an exchange built from it
     (`DATA_LICENSING.md` §1). Derived scalars only.
   - NEVER report a number without THE DIGEST that produced it. Not "the pinned image" —
     the digest. This file has pinned three different builds, and ADR-189 amendment 1 once
     said "in a digest-pinned container" while naming no digest, which left its numbers
     attributable to the wrong build until it was caught. `mgcv_version` is not enough
     either: builds 1-7 share mgcv 1.9.4 and were not host-independent.
   - NEVER commit a number measured on TIER 1 (local apt R). Different mgcv release,
     different BLAS. Tier 1 answers "is this hypothesis coherent"; tier 3 answers "is it
     true". Promoting a tier-1 number because the CI round trip felt slow is the specific
     failure this section exists to prevent, and it costs one minute to avoid.
   - NEVER change an existing test assertion to make it pass.

== QUALITY GATE ==

8. uv run ruff format src/ tests/
   uv run ruff check src/ tests/ --fix
   uv run pytest tests/ -v --tb=short -m "not slow"
   uv run pytest tests/qa/ -v --tb=short

   Then the conformance run again.

   THE AUTHORITATIVE GOLDEN GATE IS `tests/qa/test_pipeline_golden.py`, run by the
   `pytest tests/qa/` line above. It prices ALL FIVE committed configs (`flat`, `yrt`,
   `coins`, `policy_cession`, `fw_coins`) through the CLI's own parser and compares
   `golden_runner`'s distilled digest against `tests/qa/golden_outputs/` within tolerance.

   A `polaris price -o` dump is a HUMAN SPOT-CHECK ONLY, and never a byte diff:

     uv run polaris price --inforce data/qa/golden_inforce.csv \
       --config data/qa/golden_config_flat.json -o /tmp/dev_check.json
     # read summary.total_pv_profits_cedant / _reinsurer and confirm they look sane

   **The `-o` dump and `golden_outputs/` are DIFFERENT SCHEMAS** — the dump is the full
   nested result (cohorts / summary / rated_block / per-year arrays), the goldens are a
   distilled digest. Diffing them directly always differs, and doing so produced a false
   four-config "regression" report on PR #180. Do not repeat it.

   `tests/qa/` goldens must be BYTE-IDENTICAL. This engine is new code beside the
   existing one (PLAN Anchor 7); if a golden moves, something was re-pointed that
   should not have been, and that is a stop-and-revert, not a re-baseline.

   mypy is CI's job — do not chase the inherited baseline. Act only on errors your
   change newly introduces.

== DELIVER ==

9. Conventional commit, then:
   - append ONE `perf/history.jsonl` row on the INITIAL open of a PR only (ADR-177,
     step 14b of daily-dev — same rules, including the skip on review-feedback updates)
   - push to the environment-designated branch and open a DRAFT PR
   - `docs/DEV_SESSION_LOG_{date}_{slug}.md`, with these sections in addition to
     daily-dev's: **Gap Before**, **Gap After**, **Hypotheses Tried** (including the
     failures), **Oracle Version**
   - harvest follow-ups into the latest PRODUCT_DIRECTION, with the order-classification
     cap (1st-order promote, 2nd-order NICE-TO-HAVE, 3rd-order parked)
   - update `docs/CONTINUATION_mgcv_parity_engine.md`

== GUARDRAILS ==

- NEVER merge your own PR. Draft only.
- The conformance CI gate blocks on levels 1-3 and annotates 4-5. Do not narrow
  `REQUIRED_LEVELS` to go green; widening it is a reviewable edit, narrowing it is the
  move the epic has already refused twice.
- One slice per session. If a slice proves larger than the PLAN assumed, say so and ship
  the part that stands alone — do not half-build a basis.
- If uncertain about the mathematics, document the uncertainty and mark the code TODO.
  Do NOT guess at a penalty derivation. A wrong `S` that fits is worse than no `S`.
- Wall clock: if the session would exceed its budget, stop at a stop condition from step
  6 and write the characterisation. An unfinished measurement recorded honestly is worth
  more than a rushed fix.
```

---

## The conformance ledger

`docs/CONFORMANCE_LEDGER.md`, append-only, one row per hypothesis tried:

| date | slice | hypothesis | the one change | metric | before | after | tier + digest | verdict |
|---|---|---|---|---|---|---|---|---|

The `tier + digest` column is not bookkeeping. Without it, a row measured on local apt R
and a row measured on the pinned image read identically, and the ledger's whole purpose —
stopping session N+3 from re-running session N's dead end — depends on a later reader being
able to tell whether a "no movement" verdict was a real result or a tier-1 artefact.

**Why it exists.** This epic will involve reading `mgcv`'s constraint and reparameterisation
machinery and getting it wrong several times. Without a ledger, session N+3 re-runs session
N's dead end and calls it new information. The failures are the reusable part.

## What the routine may and may not decide

**May decide:** which hypothesis to test next; how to structure a basis module; what
tolerance a *newly measured* quantity is compared against, provided the tolerance is
derived and the derivation is written down.

**May not decide:** whether a term belongs in the target model form; the duration
treatment on real data (band as factor, or band as ordered numeric via a representative
value) — that is a modelling judgement the maintainer has reserved; whether to relax an
acceptance criterion; whether `select = TRUE` or `bam(discrete = TRUE)` enter scope early.

## Budget

1 run/day, alongside the existing nightly / daily-dev / pr-review / qa-on-pr set. This
routine replaces daily-dev's slot on days when the parity epic is the active work rather
than adding to it — the ACTIVE EPIC rule means only one of them has work to do.
