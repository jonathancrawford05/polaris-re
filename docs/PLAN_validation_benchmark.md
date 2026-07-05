# PLAN: Validation & Benchmark Pack (A1′)

**Status:** IN PROGRESS — constituted 2026-07-05 as the active epic per
`COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md` §5. Slice 1 (validation framework +
closed-form seed set) is **DONE** this session (ADR-130); Slice 2 is NEXT.

**Source / derivation.** The modeling roadmap (ROADMAP Phases 1–5; all
2026-06-18 Tier-A epics A1/A2/A3, C0 Asset/ALM, B3 expense-allowance) is
COMPLETE. The regenerated commercial-viability review re-ranked the catalogue and
found the frontier has moved from *modeling* to *trust-and-deployment*, with the
**Validation & Benchmark pack (A1′, ★★★★★)** the highest-value unshipped item:
Polaris RE's thesis is a *credible* AXIS/Prophet alternative, yet there was no
published numerical validation that its reserves/APVs/IRRs/capital match an
authoritative reference. The review recommended demoting the interest-exactness
epic (Reserve-Basis Correctness Slices 2–3) to a NICE-TO-HAVE follow-up and
constituting this epic next.

**Maintainer-reserved redirect (important).** The `CONTINUATION_reserve_basis_correctness`
Open Question reserved the interest-exactness → productization *redirect* for the
maintainer. Per the review §5, the correct autonomous action absent that decision
is to **constitute this epic as the active driver while leaving the
interest-exactness CONTINUATION open-but-deprioritised** — not to kill it. If the
maintainer prefers to finish interest-exactness first, its PLAN/CONTINUATION
remain intact and ship unchanged; this epic then parks behind it.

## Overall Goal

Deliver an **executable-in-CI validation suite** plus a **published validation
report** demonstrating that Polaris RE reproduces authoritative actuarial
reference values — closed-form textbook identities, published statutory reserve
decks (VM-20 / CRVM worked examples, SOA illustrative values), and (only where a
reference output is obtainable) an AXIS/Prophet side-by-side. The deliverable a
diligence team can run and read: "here is the reference, here is the engine, here
is the (tiny) difference."

## Scoping outcome (which references are obtainable & CI-executable)

The §5 scoping pass resolves what is tractable *without external network at CI
time*:

- **Closed-form textbook identities** — OBTAINABLE NOW. Constant-force and
  de Moivre APVs/annuities/premiums are mathematical identities encodable
  directly; no download, no recalled numbers. **This is Slice 1** (shipped).
- **Published regulatory / textbook table decks** (VM-20 reserve examples, SOA
  Illustrative Life Table APVs, closed-form textbook cases on a named table) —
  OBTAINABLE as *vendored constants with citations*, encoded once into
  `data/validation/` with a provenance note. **Slice 2.** Risk: the exact
  published figures must be transcribed carefully (guardrail: cite the source
  edition/table and the page; prefer values that are independently
  recomputable from a vendored `l_x` column so the transcription is self-checking).
- **AXIS/Prophet side-by-side** — REFERENCE-BLOCKED (no licensed tool / reference
  output in CI). Parked; revive only if a maintainer supplies a reference output.
  Fallback if the epic is otherwise reference-blocked: A2′ production hardening
  (ROADMAP 6.2, no external dependency).

## Design Anchors

- **Engine-agnostic reference models.** `ValidationCase` / `ValidationResult` /
  `ValidationReport` (ADR-130) hold the reference + tolerance + provenance; the
  caller drives the engine. Later slices add cases, not new model plumbing.
- **References are identities or cited constants, never guessed.** Closed-form
  cases assert to machine precision (`rtol=1e-9`); textbook/deck cases carry a
  documented `tolerance_rationale` for any modelling-convention gap.
- **Goldens stay byte-identical throughout.** A validation pack never touches the
  pricing path; every slice is pricing-neutral until — and including — the
  surfacing slice.

## Decomposition

### Slice 1: Validation framework + closed-form seed set — DONE (2026-07-05, ADR-130)
`polaris_re.analytics.validation`: `ValidationCase`/`ValidationResult`/
`ValidationReport` + `run_closed_form_benchmarks()`. Seed: constant-force
term-insurance APV and temporary annuity-due APV vs exact discrete closed forms
(machine precision), plus the term-insurance APV vs the continuous-force textbook
identity (documented ~0.2% discretisation tolerance). 18 tests in
`tests/validation/test_closed_form_pack.py`. Goldens byte-identical.

### Slice 2: Published-deck reference set — NEXT
- **Depends on:** Slice 1 merged.
- Add the `STATUTORY_DECK` case family (category already reserved). Vendor a small
  reference table (e.g. the SOA Illustrative Life Table `l_x` at i=6%, or a
  published VM-20/CRVM reserve example) into `data/validation/` with a citation
  header; encode `ValidationCase`s for whole-life `A_x`, annuity `ä_x`, and net
  premium `P_x` (and/or a published reserve factor). Where feasible, make the
  expected value *independently recomputable* from the vendored `l_x` so the
  transcription self-checks.
- **Guardrail:** if the pack adds files under `data/`, update the Dockerfile
  `COPY` and `.dockerignore` allowlist in the same PR (recurring trap, PR #61/#66).
- **Acceptance:** engine `A_x`/`ä_x`/`P_x` (or a reserve factor) reproduce the
  published values within a documented tolerance; report spans all three
  categories; goldens byte-identical.

### Slice 3: Surface the report — PLANNED
- **Depends on:** Slice 2 merged.
- `polaris validate` CLI command that runs `run_closed_form_benchmarks()` (+ the
  deck cases) and prints/exports the Markdown report; a `05_validation_report.ipynb`
  notebook rendering the pass/fail table for diligence; ARCHITECTURE note. HARVEST
  FOLLOW-UPS, then Status → COMPLETE.

### Slice 4 (optional): AXIS/Prophet side-by-side — PARKED (reference-blocked)
Only if a maintainer supplies a reference output. Otherwise the epic closes at
Slice 3.

## Open Questions (for human)

- **Redirect go/no-go (still reserved from the checkpoint):** accept the review's
  recommendation to make this the active epic and demote interest-exactness to a
  NICE-TO-HAVE follow-up? Default (taken this session): yes, this is the active
  epic; interest-exactness parked open. If you'd rather finish interest-exactness
  first, say so and the next session ships its Slice 2 instead.
- **Slice 2 reference choice:** prefer the SOA Illustrative Life Table (clean
  textbook APVs, widely cited) or a published VM-20/CRVM reserve deck (closer to
  the "reproduce the cedant's held reserve" use case)? Either is CI-tractable as a
  vendored, cited constant.
