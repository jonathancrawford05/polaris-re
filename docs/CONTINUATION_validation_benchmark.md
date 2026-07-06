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
- **Status:** DONE
- **Branch:** `claude/loving-gauss-alct0t`
- **PR:** (this session's PR)
- **What was done:** Vendored the **SOA Illustrative Life Table** `l_x`
  (`data/validation/illustrative_life_table.csv`, ages 0..121, closed at
  `l_121=0`), generated from the table's *published Makeham law* (`A=.0007`,
  `B=.00005`, `c=10^.04`, `l_0=100000`) — the constants are the citation, so no
  hand-copied column. Nine `STATUTORY_DECK` cases (issue ages 35/40/65) reproduce
  the whole-life `A_x`, annuity-due `ä_x`, and net level premium `P_x = A_x/ä_x`
  at `i=6%`, driving the **WholeLife** engine to omega and reconstructing the
  annual APVs from the monthly output (machine precision, `rtol=1e-9`, measured
  ~2e-14). Added `run_statutory_deck_benchmarks()` and a combined
  `run_full_validation_pack()`. ADR-131. Dockerfile `COPY data/validation/` +
  `.dockerignore` allowlist updated in the same PR.
- **Key decisions (affect later slices):**
  - `run_full_validation_pack()` is the single entry point Slice 3's CLI/notebook
    should call — it concatenates closed-form + deck into one report spanning all
    three categories.
  - The vendored table is regenerated from the Makeham law and self-checked, so
    the CSV is reproducible; the printed-ILT anchors (`1000A_35=128.72`,
    `ä_35=15.3926`, …) are asserted to confirm it IS the ILT.
  - The engine's *native monthly* `A^{(12)}_x`/`ä^{(12)}_x` differ from the annual
    table by the standard `i/i^{(12)}` acceleration (~2.7%) and the `11/24`
    annuity offset — a documented convention gap, not a failure; the annual
    reconstruction is the anchor.

### Slice 3: Surface the validation report
- **Status:** NEXT
- **Depends on:** Slice 2 merged.
- **Scope:** `polaris validate` CLI — call `run_full_validation_pack()`,
  print/export the Markdown report; **non-zero exit on any FAIL**; a
  `notebooks/05_validation_report.ipynb` rendering the pass/fail table for
  diligence; ARCHITECTURE note. Run HARVEST FOLLOW-UPS, then Status → COMPLETE.

### Slice 4 (optional): AXIS/Prophet side-by-side
- **Status:** PARKED (reference-blocked)
- Only if a maintainer supplies a reference output; otherwise the epic closes at
  Slice 3.

## Context for Next Session

- **Start here:** Slice 3 — surface the report. `run_full_validation_pack()` is
  the single entry point; wire it to a `polaris validate` CLI command (Typer)
  that prints `report.to_markdown()`, optionally writes it to `-o`, and exits
  non-zero when `not report.all_passed`. Add `notebooks/05_validation_report.ipynb`
  rendering the table. No new references needed — Slices 1+2 provide 13 cases
  across all three categories.
- Slice 3 is a **surfacing** slice: it must not change any expected value or
  touch the pricing path. Goldens stay byte-identical.
- The deck loader (`_load_illustrative_life_table`) resolves the vendored CSV via
  `$POLARIS_DATA_DIR/validation/` first, else the repo-relative `data/validation/`.
  The CLI runs from an installed package, so confirm the path resolves in the
  Docker image (the `COPY data/validation/` is already in the Dockerfile).

## Open Questions (for human)

- **Redirect go/no-go (reserved from the Reserve-Basis Correctness checkpoint):**
  confirm A1′ validation is the active epic (default taken across Slices 1–2) vs
  finishing interest-exactness first. Still unresolved; the epic continues under
  the default until the maintainer decides.
- **Reserve-factor deck (optional):** the ILT deck validates APV/premium columns.
  A published VM-20/CRVM *held-reserve* worked example — closer to the "reproduce
  the cedant's held reserve" use case — is a candidate additional deck, not
  required to close the epic. (Slice 2's reference-choice question is otherwise
  resolved: SOA Illustrative Life Table was chosen.)

## Refinement Backlog

(harvest into PRODUCT_DIRECTION when this CONTINUATION closes)

- AXIS/Prophet side-by-side validation case (reference-blocked; revive on a supplied
  reference output). *Already harvested 2026-07-05 as NICE-TO-HAVE.*
- WholeLife-to-omega closed-form validation case (extend coverage beyond TermLife).
  *Already harvested 2026-07-05 as NICE-TO-HAVE; candidate for Slice 2.*
