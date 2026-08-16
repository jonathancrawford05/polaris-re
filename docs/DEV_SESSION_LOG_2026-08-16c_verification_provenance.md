# Dev Session Log — 2026-08-16c

## Item Selected

- **Source:** maintainer direction, following the PR #199 review
- **Priority:** BLOCKER — the parity epic's verification contract
- **Branch:** `claude/eloquent-ride-hkn604` (based on PR #199's head `439fef3`, so this
  PR stacks on #199 and should merge after it)
- **Type:** not an epic slice — a cross-cutting standard the epic (and every future
  comparison) depends on. It is the direct remediation of a defect the PR #199 review
  surfaced, so it is neither fallback nor polish.

## Gap Before

The `mgcv` parity epic exists to prove this engine reproduces `mgcv`. Two consecutive
slices shipped comparison tables that could not structurally demonstrate that — and the
second had been carved out specifically to repair the first:

- **Slice 1** (`raw`/`paraPen`): Python builds `X` and `S`, writes them to the exchange,
  and mgcv is fitted *on them* (`y ~ 0 + X + offset(off)`, `paraPen`,
  `scalePenalty=FALSE`). `predict(type="lpmatrix")` and `m$paraPen$S` hand them straight
  back. Only `rank` is computed on both sides.
- **Slice 1b** (mgcv-native): `extract_smooth_terms` parses the R payload;
  `compare_term_extract` compares the result against that same payload. Structurally
  zero, every column.

Nothing was misstated. Docstrings, session logs, the ledger and the CI caption all said
"packaging, not verification." The mislabelling propagated regardless — **the caveat did
not travel and the zeros did** — into the CI job summary, the ledger's "agrees" column,
the PR body, and an automated review that approved on it.

Verified before writing anything: `grep` for a cubic-regression-spline construction
across `src/polaris_re/analytics/` returns nothing. The only Python basis is
`PenalizedTensorMIModel._basis` — a B-spline/P-spline (scipy `BSpline` / patsy `bs`) with
difference penalties, a different construction from Wood's `cr`. So the Python side
genuinely cannot produce these results independently today.

## Gap After

- **The taxonomy, in the type.** `src/polaris_re/core/verification.py`:
  `ComparisonProvenance` (INDEPENDENT / ECHO / TRANSPORT), `ComparedQuantity` (refuses
  INDEPENDENT when both sides name the same producer), `VerificationClaim` (per-quantity
  provenance, so one table can carry an independent column beside echoed ones),
  `require_parity_evidence` (the gate), `evidence_headline` / `evidence_markdown` (the
  headline a report prints, *derived* from the declaration).
- **Both Stage-A paths declare honestly.** `TermExtract` carries a required
  `evidence: VerificationClaim` with **no default**, so a new producer cannot be written
  without answering "who computed each side?". `RAW_PATH_CLAIM` marks `design_X`/
  `penalty_S` as ECHO with `rank` INDEPENDENT; `SMOOTH_PATH_CLAIM` marks every column
  TRANSPORT.
- **The CI job summary now says it.** Verified by extracting the workflow's embedded
  script and running it against a real `gam_term_extract.json` (R 4.3.3 / mgcv 1.9.1
  installed locally for this session). The slice-1 table now prints *"Harness check with
  one parity column — NOT basis parity. Parity evidence: `rank`."* and the slice-1b table
  *"Harness check — NOT parity. No column here is independently produced."*
- **The rule generalises.** `docs/VERIFICATION_STANDARD.md` is written for "any
  reference implementation," with the mechanical signature test, the required claim
  sentence, acceptance-criteria wording, ledger requirements, what review checks, and a
  §5 audit of where the project actually stands. Hooked into `CLAUDE.md` (reading list +
  three `Never` entries) and `REVIEW.md` (a P0 and two P1 categories).
- **Slice 2 rescoped** as the epic's first parity slice, with acceptance criteria that
  name provenance and encode the mechanical test.

## Hypotheses Tried

1. **Can the Python side produce these results independently today?** Measured, not
   assumed: `extract_smooth_terms(terms, r_terms)` takes the reference payload as an
   argument; no `cr` basis exists anywhere in `src/`; this PR's predecessor does not
   touch `experience_gam_penalized.py`. **CONFIRMED: no.**
2. **Is the epic tautological overall?** No — and the standard says so explicitly rather
   than overstating the problem. `LEVEL_METRICS` (levels 1-5) compares `eta`,
   coefficients, `edf`/`tr(F)`, `Vb` and selected λ between two independently implemented
   fitters over a shared `(X, S)`. That is real parity evidence, which is why level 4 can
   genuinely *disagree* (ADR-190's Kass-Steffey gap). **The fitter has independent
   evidence; the bases have none.**
3. **Would the new gate have caught slice 1b?** Yes, and it is pinned as a test:
   `test_a_parity_claim_over_the_mgcv_native_path_is_refused` — `require_parity_evidence`
   over `SMOOTH_PATH_CLAIM` raises rather than passing.

## What Was Done

1. `src/polaris_re/core/verification.py` — the primitive (new).
2. `src/polaris_re/core/__init__.py` — exports.
3. `src/polaris_re/analytics/gam_stage_a.py` — `RAW_PATH_CLAIM`, `SMOOTH_PATH_CLAIM`,
   required `TermExtract.evidence`, `TermExtractComparison.evidence`.
4. `.github/workflows/mgcv-conformance.yml` — provenance legend above both diff tables,
   captions corrected.
5. `docs/DECISIONS.md` — **ADR-193**.
6. `docs/VERIFICATION_STANDARD.md` — the project-wide standard (new).
7. `CLAUDE.md`, `REVIEW.md`, `docs/CONFORMANCE_LEDGER.md` — the hooks.
8. `docs/ROUTINE_CHANGES_2026-08-16_verification_provenance.md` — the five routine-prompt
   edits for the human trigger owner (new).
9. `docs/PLAN_mgcv_parity_engine.md`, `docs/CONTINUATION_mgcv_parity_engine.md` — slice 2
   rescoped; slice 1b annotated as harness.
10. `docs/PRODUCT_DIRECTION_2026-07-24.md` — harvest, with order tags.

## Tests Added

- `tests/test_core/test_verification.py` — 21 tests: the taxonomy; `ComparedQuantity`
  refusing a single-producer independence claim and unnamed producers; `VerificationClaim`
  splitting parity from harness quantities, refusing duplicates/empties;
  `require_parity_evidence` passing independent evidence and refusing ECHO/TRANSPORT; the
  three derived headlines; markdown rendering and its determinism.
- `tests/test_analytics/test_gam_stage_a.py` — 5 added: the raw path declaring ECHO with
  `rank` as its one parity column, the mgcv-native path declaring TRANSPORT throughout,
  the parity gate refusing slice 1b's claim, and provenance carrying through a comparison.

## Baseline and end state

| | |
|---|---|
| Baseline (PR #199 head `439fef3`, this environment) | **3352 passed, 8 skipped, 0 failed** — the 5 pre-existing `data/mortality_tables` failures do not occur here because `scripts/convert_soa_tables.py` reached pymort (6/6 SOA tables converted). Measured *before* R was installed, so the R-gated tests skipped. |
| End state | **3381 passed, 5 skipped, 0 failed** = 3352 + 26 new + 3 that stopped skipping once R 4.3.3 / mgcv 1.9.1 was installed mid-session (the two Stage-A end-to-end proofs and one sibling gate). No new or changed failures. |
| `tests/qa/` | 120 passed / 2 skipped, goldens byte-identical — untouched. |
| Perf row | one row appended (ADR-177); `src/` touched, so the docs-only exemption does not apply. |

## Impact on Golden Baselines

None. `tests/qa/golden_outputs/` untouched; nothing in `products/`, `reinsurance/` or the
CLI moved. The one behavioural change is that `TermExtract` now requires an `evidence`
field — a Stage-A harness type introduced in slice 1, with no pricing path through it.

## Open Questions / Follow-ups

Harvested into `docs/PRODUCT_DIRECTION_2026-07-24.md` under "Harvested 2026-08-16b".

1. **The five routine-prompt edits** must be applied by the human who owns the triggers —
   the prompts live outside this repo. Until then the standard binds the code but not the
   sessions that write it. 1st-order.
2. **Slice 2 is now the epic's first parity slice**, rescoped in the PLAN. 1st-order.
3. **The epic's evidence audit** (§5 of the standard) is a statement of current state,
   worth re-reading before any claim about what the epic has proven. 2nd-order,
   NICE-TO-HAVE.

## Parked Polish

None.
