# Continuation: Validation & Benchmark Pack (A1′)

**Source:** `COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md` §4–§5 (Tier-A A1′) —
IMPORTANT / ★★★★★. Constituted per routine step 5b as the active epic after the
post-Slice-1 checkpoint of the Reserve-Basis Correctness epic recommended
redirecting from interest-exactness to productization. See
`docs/PLAN_validation_benchmark.md`.
**Status:** IN PROGRESS
**Total slices:** 3 (+ optional Slice 4, parked)
**Estimated total scope:** ~8–12 dev-days

## Overall Goal

Deliver an executable-in-CI validation suite + a published validation report
demonstrating that Polaris RE reproduces authoritative actuarial reference values
(closed-form textbook identities; published statutory reserve decks / SOA
illustrative values; AXIS/Prophet side-by-side only where a reference output is
obtainable). Backs the README's "credible open-source alternative to AXIS/Prophet"
thesis — the single biggest remaining *credibility* gap now that the modeling
roadmap (Phases 1–5) is complete.

## Active-epic note (redirect reserved for the maintainer)

This epic is the **active driver**. The prior active epic
(`CONTINUATION_reserve_basis_correctness`) is **parked open-but-deprioritised**
(not killed) pending the maintainer's redirect go/no-go. If the maintainer
declines the redirect, interest-exactness resumes and its Slice 2 ships unchanged;
this epic then parks behind it.

## Decomposition

### Slice 1: Validation framework + closed-form seed set
- **Status:** DONE
- **Branch:** `claude/loving-gauss-bab9og`
- **PR:** (this session's PR)
- **What was done:** New `polaris_re.analytics.validation` module —
  `ValidationCase` (reference value + source + tolerance/rationale),
  `ValidationResult`, `ValidationReport` (scored, `to_markdown()`), and
  `run_closed_form_benchmarks()`. Seed set (constant force of mortality):
  term-insurance APV and temporary annuity-due APV vs exact discrete
  geometric-series closed forms (machine precision, `rtol=1e-9`), plus the
  term-insurance APV vs the continuous-force textbook identity (Bowers §4.2;
  documented `rtol=5e-3` for the ~0.2% monthly-discretisation gap). 18 tests
  (`tests/validation/test_closed_form_pack.py`). ADR-130.
- **Key decisions (affect later slices):**
  - The reference models are **engine-agnostic** — a case holds only the
    reference; the caller drives the engine. Slice 3's CLI/notebook reuse them
    unchanged; Slice 2 adds cases, not plumbing.
  - `ValidationCategory` already reserves `STATUTORY_DECK` for Slice 2.
  - References must be **identities or cited constants, never guessed** — the
    verify-premise reproduction is run before encoding any expected value.
  - Validated via **TermLife** (simplest engine); a WholeLife closed-form case is
    a candidate Slice-2 addition.

### Slice 2: Published-deck reference set (`STATUTORY_DECK`)
- **Status:** NEXT
- **Depends on:** Slice 1 merged.
- **Files to create/modify:**
  - `data/validation/<table>.csv` — a small vendored reference table (e.g. SOA
    Illustrative Life Table `l_x` at i=6%, or a published VM-20/CRVM reserve
    example) with a citation header (source edition + table/page).
  - `src/polaris_re/analytics/validation.py` — `STATUTORY_DECK` cases for
    whole-life `A_x`, annuity `ä_x`, net premium `P_x` (and/or a reserve factor);
    a loader that reads the vendored deck.
  - `Dockerfile` `COPY` + `.dockerignore` allowlist — **in the same PR** if any
    `data/` file is added (recurring trap, PR #61/#66).
  - `tests/validation/` — deck cases + a self-check that the expected APVs are
    independently recomputable from the vendored `l_x` (guards transcription).
- **Tests to add:** engine `A_x`/`ä_x`/`P_x` (or reserve factor) reproduce the
  published values within a documented tolerance; report spans all three
  categories; independent-recompute self-check; goldens byte-identical.
- **Acceptance criteria:**
  - At least one published/textbook table deck reproduced within a documented,
    justified tolerance.
  - `ValidationReport` includes `STATUTORY_DECK` cases and still `all_passed`.
  - Goldens/QA byte-identical (validation pack never touches the pricing path).

### Slice 3: Surface the validation report
- **Status:** PLANNED
- **Depends on:** Slice 2 merged.
- **Scope:** `polaris validate` CLI (runs the pack, prints/exports the Markdown
  report; non-zero exit on any FAIL); a `notebooks/05_validation_report.ipynb`
  rendering the pass/fail table for diligence; ARCHITECTURE note. Run HARVEST
  FOLLOW-UPS, then Status → COMPLETE.

### Slice 4 (optional): AXIS/Prophet side-by-side
- **Status:** PARKED (reference-blocked)
- Only if a maintainer supplies a reference output; otherwise the epic closes at
  Slice 3.

## Context for Next Session

- **Start here:** Slice 2. First decide the reference (SOA Illustrative Life Table
  vs a published VM-20/CRVM deck — see Open Questions). Prefer a table whose
  expected APVs are *independently recomputable from a vendored `l_x`*, so the
  transcription self-checks and there is zero guessing.
- The `evaluate`/`ValidationReport` machinery is done — Slice 2 only adds
  `ValidationCase`s + a deck loader + the `data/` vendoring (with the Dockerfile /
  `.dockerignore` update in the same PR).
- Whole-life APV via the engine: the WholeLife net-single-premium / reserve path is
  more involved than TermLife (omega machinery, monthly recursion) — if adding a WL
  closed-form case, reproduce it in a scratch script first (verify-premise) as was
  done for the TermLife cases.

## Open Questions (for human)

- **Redirect go/no-go (reserved from the Reserve-Basis Correctness checkpoint):**
  confirm A1′ validation is the active epic (default taken this session) vs finishing
  interest-exactness first.
- **Slice 2 reference choice:** SOA Illustrative Life Table (clean textbook APVs,
  widely cited) vs a published VM-20/CRVM reserve deck (closer to the "reproduce the
  cedant's held reserve" use case)?

## Refinement Backlog

(harvest into PRODUCT_DIRECTION when this CONTINUATION closes)

- AXIS/Prophet side-by-side validation case (reference-blocked; revive on a supplied
  reference output). *Already harvested 2026-07-05 as NICE-TO-HAVE.*
- WholeLife-to-omega closed-form validation case (extend coverage beyond TermLife).
  *Already harvested 2026-07-05 as NICE-TO-HAVE; candidate for Slice 2.*
