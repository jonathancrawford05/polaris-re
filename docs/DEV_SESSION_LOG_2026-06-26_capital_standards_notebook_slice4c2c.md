# Dev Session Log — 2026-06-26 (Three-standard capital validation notebook, Epic 3 Slice 4c-2c — EPIC COMPLETE)

## Item Selected
- **Source:** `CONTINUATION_cross_jurisdiction_capital.md` (active Epic 3,
  Tier-A A3) — Slice 4c-2c; backed by `PLAN_cross_jurisdiction_capital.md`,
  `PRODUCT_DIRECTION_2026-06-18.md` IMPORTANT, and
  `COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` Tier-A A3.
- **Priority:** IMPORTANT
- **Title:** Three-standard validation notebook comparing LICAT / RBC /
  Solvency II — the final slice of the cross-jurisdiction capital epic.
- **Slice:** 4c-2c (final) — **closes Epic 3**.
- **Branch:** `claude/awesome-bardeen-kmtzts` (environment-designated; the
  routine's `feat/auto-*` default is overridden by the remote-session designated
  `claude/*` branch per step 8 ENVIRONMENT OVERRIDE).

## Selection Rationale

Step 5 found `CONTINUATION_cross_jurisdiction_capital.md` IN PROGRESS, so the
active Epic 3 IS the work selection (routine step 5c — the CONTINUATION is the
selection; skip fallback). Slice 4c-2b (PR #105) is merged to `main` (git log HEAD
`d929a79` = the PR #105 merge; the designated branch already sits there), so the
final slice 4c-2c was unblocked. No open PRs to address first
(`list_pull_requests state=open` → empty). No fallback considered — the guardrail
forbids falling back while the active Epic's next slice can advance, and it could.

`COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` is 8 days old (< 30) → no regeneration
needed. The notebook was the last planned piece of the epic, so this session both
ships it and **closes Epic 3** (CONTINUATION IN PROGRESS → COMPLETE).

## Verify Premise (step 7b)

Reproduced before writing the notebook: `ls notebooks/` showed only
`01_term_life_yrt_pricing.ipynb` and `02_reserve_basis_comparison.ipynb` — no
three-standard capital notebook existed. A prototype script confirmed the three
standards run end-to-end through `capital_model_for` + `run_with_capital` on a real
projected block and produce distinct, sensible numbers (LICAT peak $750K, RBC
$7.5K, EU $13.9K on $5M NAR; LICAT solvency ratio 120% with $900K available
capital; ratio linear 2.00x on doubling). The premise holds — the demonstration
artifact was genuinely missing, and the surfaces it consumes work.

A second finding from reproduction (NOT a defect): the ~100x cross-standard level
gap is **by design** of the committee-stage placeholder factors — LICAT's default
C-2 is a 10% mortality *shock* on NAR (`capital.py:133`), while RBC (`0.00150`,
`rbc.py:148`) and Solvency II (`0.0020`, `solvency2.py:203`) are small ongoing
factors. Documented in ADR-098/100 as placeholders pending the Asset/ALM epic. The
notebook surfaces this honestly rather than masking it (see ADR-107).

## Decomposition Plan (multi-session — epic now complete)

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | US RBC core + `CapitalModel`/`CapitalSchedule` protocols | ✅ Done | #92 |
| 2 | Widen `ProfitTester`/`Portfolio` `run_with_capital` to protocol | ✅ Done | #98 |
| 3 | Solvency II SCR module | ✅ Done | #99 |
| 4a | CLI + API `--capital {licat,rbc,solvency2}` selector | ✅ Done | #100 |
| 4b | Dashboard selector + Excel jurisdiction label | ✅ Done | #101 |
| 4c-1 | Result-level capital-ratio core (protocol + `ProfitTester`) | ✅ Done | #102 |
| 4c-2a | CLI + API available-capital numerator | ✅ Done | #103 |
| 4c-2b | Excel ratio row + dashboard input/tile | ✅ Done | #105 |
| 4c-2c | Three-standard validation notebook | ✅ Done | (this PR) |

## What Was Done

Added `notebooks/03_capital_standards_comparison.ipynb`, the demonstration
artifact that closes Epic 3. It prices one self-contained term block (10 policies,
$5M face, flat synthetic mortality + lapse — no CSV load) and compares LICAT / US
RBC / EU Solvency II side by side.

The notebook derives the Net Amount at Risk transparently
(`max(face·inforce_ratio − reserve, 0)` — the same formula the YRT treaty uses)
and feeds the **identical** NAR to all three standards via
`capital_model_for(id, ProductType.TERM)` +
`ProfitTester.run_with_capital(..., nar=, available_capital=)`, so the comparison
isolates the capital factors. It tabulates: the required-capital run-off
(`capital_by_period` at issue / yr 1 / 5 / 10 / 15), peak and PV capital, return
on capital, and the regulatory solvency ratio.

**Honest presentation of un-calibrated standards (ADR-107).** Rather than hand-tune
factors to make the levels line up, the notebook surfaces the ~100x cross-standard
level gap as its explicit teaching point — a leading calibration caveat and a
demonstration that the solvency ratio is meaningful *within* a standard (linear in
available capital: $900K → 120% LICAT, $1.8M → 240%, exactly 2.00x) but not
comparable in *level* across standards until the Asset/ALM calibration epic. This
matches the placeholder disposition the LICAT/RBC/SCR modules already document.

No `src/` change — the notebook consumes only existing, closed-form-tested surfaces.
Built and executed via a small nbformat builder (nbconvert/nbclient are not
installed in this environment); the committed `.ipynb` carries the executed outputs
and validates as nbformat v4. All 8 code cells execute top-to-bottom cleanly.

## Files Changed

- `notebooks/03_capital_standards_comparison.ipynb` — new (the deliverable).
- `docs/DECISIONS.md` — ADR-107.
- `docs/PLAN_cross_jurisdiction_capital.md` — Slice 4c-2c SHIPPED; top status
  banner → COMPLETE.
- `docs/CONTINUATION_cross_jurisdiction_capital.md` — Slice 4c-2c DONE; **Status
  IN PROGRESS → COMPLETE** (after harvest, per the guardrail).
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — harvest (new cross-standard
  factor-calibration follow-up) + ledger healing (struck the now-fully-shipped
  result-level solvency-ratio surface entry with a SHIPPED footer).
- `docs/DEV_SESSION_LOG_2026-06-26_capital_standards_notebook_slice4c2c.md` — this
  log.

## Tests Added

None — notebooks are dev/demonstration artifacts (omitted from coverage in
`pyproject.toml`, launched via `make notebook`), matching the `01`/`02` notebook
precedent. The notebook adds no new calculation; every surface it calls is already
closed-form tested (`TestRunWithCapitalRatio`, the per-result ratio tests in
`test_capital`/`test_rbc`/`test_solvency2`, the linearity tests in
`test_pricing_solvency_ratio` and `test_cli`/`test_main`). Its verification is that
it executes top-to-bottom cleanly, which it does.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| Notebook compares LICAT / RBC / Solvency II on one block | ✅ | `03_capital_standards_comparison.ipynb` |
| Shows required-capital run-off side by side | ✅ | `capital_by_period` at issue/yr1/5/10/15 |
| Shows RoC side by side | ✅ | peak/PV capital + RoC table |
| Shows the new solvency ratio side by side | ✅ | with the cross-standard caveat |
| Identical NAR drives all three (isolates factors) | ✅ | one `nar_vec`, fed via `nar=` |
| Executes top-to-bottom cleanly | ✅ | 8 code cells, nbformat-valid, outputs embedded |
| Own ADR | ✅ | ADR-107 |
| Goldens byte-identical | ✅ | no `src/`/`data/`/test change; QA 76, fast 1664 |
| Epic closed | ✅ | CONTINUATION COMPLETE (after harvest) |

## Open Questions / Follow-ups

- **Epic 3 is COMPLETE.** With reserve-basis (A1), IFRS 17 movement
  (`CONTINUATION_ifrs17_movement.md` — COMPLETE), and cross-jurisdiction capital
  (A3) all closed, the next routine session reaches step 5b with **no active Epic**
  and must START the next-ranked unstarted Tier-A item from
  `COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` (writing `PLAN_<feature>.md` + shipping
  slice 1 is that session's deliverable). If the review is then > 30 days old
  (it is dated 2026-06-18), regenerate it first per step 6. The next session should
  re-rank the Tier-A table against shipped work before picking — do not default to
  "smallest available".
- **Cross-standard factor calibration (Asset/ALM epic).** Newly harvested to
  PRODUCT_DIRECTION (NICE-TO-HAVE) — the notebook made the ~100x level gap concrete.
- **Held-capital basis** (target multiple of ACL as an alternative numerator form)
  and **per-side numerator** — both already tracked in PRODUCT_DIRECTION; not
  re-promoted (no duplication).

## Parked Polish

None. The harvested calibration item is 1st-order (a follow-up of the
originally-planned Epic 3 capital feature); the held-capital and per-side items are
already in the queue. No 3rd-order-or-deeper item arose.

## Impact on Golden Baselines

None. No `src/`, `data/`, or test change — the notebook is a pure dev artifact.
Full fast suite 1664 passed (unchanged from the post-4c-2b baseline); QA golden
suite 76 passed; `ruff format`/`check` clean on `src/`+`tests/`. No baseline
regenerated.

## Harvest (step 17 / 18 — CONTINUATION closing)

This slice closes `CONTINUATION_cross_jurisdiction_capital.md`, so per step 18 the
harvest ran BEFORE the IN PROGRESS → COMPLETE transition. Surviving items:
- ADR-107 "Out of scope": held-capital basis (already tracked, line 408 —
  reinforced through ADR-106), per-side numerator (already tracked, line 768), and
  **cross-standard factor calibration** → newly promoted as NICE-TO-HAVE (1st-order)
  with the ~100x-gap evidence and provenance.
- CONTINUATION Open Questions: "Held-capital basis" (already tracked) and "Factor
  calibration sign-off" (maps to the new calibration item).
- No CONTINUATION "Refinement Backlog" section existed; the Open Questions are the
  only surviving items, all now in the queue.

Ledger healing (step 4b): PRs merged since the last committed session log are #103
(4c-2a), #104 (QA harness), #105 (4c-2b). #104's PRODUCT_DIRECTION entry was
already struck SHIPPED by a prior session (line 716). #103/#105 are Epic 3 slices,
not discrete queue entries — the epic stayed IN PROGRESS until this PR closes it.
This session struck the now-fully-shipped **result-level solvency-ratio surface**
entry (line 439) with a SHIPPED (PR #106) footer, since 4c-2c completes the last
piece of that surface. Ledger healthy.

## Baseline Note

Branch `claude/awesome-bardeen-kmtzts`, HEAD at `d929a79` (PR #105 merge). Baseline
fast suite (`pytest -m "not slow"`, exit 0): **1664 passed, 110 deselected** (CIA
tables MISSING from pymort as usual; SOA + CSO converted) — matches the prior
session's recorded post-4c-2b count exactly, so no NEW/CHANGED failures; proceeded
per the tolerance-aware check. Post-change (no `src/` touched): suite unchanged at
**1664 passed**, QA golden suite **76 passed**.
