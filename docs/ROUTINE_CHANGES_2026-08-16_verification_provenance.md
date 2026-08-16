# Routine changes — verification provenance (2026-08-16)

## Why

**Any comparison this project makes against any reference must say who computed
each side.** A table of near-zero diffs looks identical whether it means "two
implementations agree", "the reference returned what we handed it", or "we parsed
our own reference's output" — and only the first is evidence of correctness.

This binds every routine, because every routine compares things:

| Comparison | The reference | Where it happens |
|---|---|---|
| Closed-form validation packs | A hand-derived actuarial formula | daily dev |
| Golden regression | **This engine's own prior output** | every routine |
| Cedant / vendor reconciliation | An external party's figures | daily dev |
| Benchmark packs | A published or hand-computed table | daily dev |
| Conformance suites | A reference implementation | the parity routine |

The rule, the machinery and the review criteria are ADR-193,
`docs/VERIFICATION_STANDARD.md` and `polaris_re.core.verification`. This file
carries the matching edits to the **routine prompts**, which live in the trigger
configuration outside this repo and must be applied by the human who owns those
triggers.

### Where the rule came from

The failure that produced it was in the `mgcv` parity epic, and it is worth
recording because the shape generalises. Two consecutive slices shipped
comparison tables that could not structurally demonstrate parity — and the second
had been carved out specifically to repair the first. In one, Polaris built the
design and penalties, handed them to the reference, and read them back. In the
other, the Python side parsed the reference's output and was then compared
against that same output.

Nothing was misstated at any point. Every docstring, session log and ledger row
said "packaging, not verification." **The caveat did not travel and the zeros
did** — into the CI job summary, the ledger's "agrees" column, the PR body, and
an automated review that approved on it.

The lesson is not "be careful with mgcv." It is that honesty at the point of
authorship is not sufficient: the artefact has to carry its own provenance.

---

## Status

| Change | Routine | State |
|---|---|---|
| 1 — comparisons against any reference | daily dev | **outstanding** |
| 2 — acceptance criteria name provenance | daily dev | **outstanding** |
| 3 — ledger rows name producers | daily dev | **outstanding** |
| 4 — the epic-ownership exclusion | daily dev | **outstanding** |
| 5 — the provenance audit | PR review | applied 2026-08-16 |
| 6 — goldens are not correctness evidence | PR review | applied 2026-08-16 |
| 7 — the provenance gate | mgcv parity | applied 2026-08-16 (and in `docs/ROUTINE_MGCV_PARITY.md` step 5b) |

---

## Change 1 — Daily Dev: comparisons against any reference

**Insert as a new step immediately before the quality gate (currently step 4).**

```
== COMPARISONS AGAINST A REFERENCE ==

If this session compares Polaris output against ANY reference — a closed-form
derivation, a benchmark table, a cedant's or vendor's figures, an external
library, a prior version of this engine — then BEFORE writing the comparison,
read docs/VERIFICATION_STANDARD.md and apply its rule.

a. WRITE THE CLAIM SENTENCE FIRST, before the code:
     "<left> computes <quantity> from <recipe>; <right> computes it via
      <call>; compared on <columns>."
   If you cannot fill it in with two DISTINCT computations, you are building a
   HARNESS, not a verification. That is legitimate work — say so in the item
   title, the PR title and the session log — but do not report it as agreement.

b. APPLY THE MECHANICAL TEST TO THE PRODUCER'S SIGNATURE, BEFORE ITS BODY:
     if the function producing one operand takes the other side's payload as an
     input, it is NOT an independent producer.
   Equally, if we SUPPLIED the quantity to the reference, reading it back is
   ECHO, not verification.

c. CLASSIFY EVERY COMPARED QUANTITY — provenance is per-column, not per-table:
     INDEPENDENT — two implementations from the same recipe. The only evidence
                   of correctness, and the only kind that can genuinely disagree.
     ECHO        — we supplied it, the reference returned it. A no-tampering
                   check.
     TRANSPORT   — one side computed it, the other parsed it. A round-trip check.

d. DECLARE IT IN THE TYPE: build a VerificationClaim
   (polaris_re.core.verification) with one ComparedQuantity per column, each
   naming both producers, and carry it on the artefact the producer returns.

e. DO NOT HAND-WRITE THE HEADLINE of any published comparison table. Call
   evidence_markdown(claim) and print it above the diffs.

f. GATE ANY ASSERTED CLAIM OF AGREEMENT with require_parity_evidence(...), so a
   harness result cannot satisfy a correctness criterion.

TWO STANDING CASES THIS ROUTINE MEETS OFTEN:

  - CLOSED-FORM PACKS are INDEPENDENT when the reference is derived separately
    (a formula written out and implemented on its own terms). A "closed form"
    that is computed by calling the function under test is circular — the same
    defect wearing a different hat. Keep the derivation independent of the
    engine path it checks.

  - GOLDEN BASELINES (tests/qa/golden_outputs/) are THIS ENGINE'S OWN PRIOR
    OUTPUT. A passing golden test means BEHAVIOUR HAS NOT CHANGED. It is never
    evidence that a number is correct, and must never be described that way in
    a session log, a PR body or an ADR.
```

## Change 2 — Daily Dev: acceptance criteria name their provenance

**Amend the work-order / PLAN authoring step.**

```
Any acceptance criterion about agreement with a reference must name the
provenance it requires, so a harness result cannot tick it:

  BAD:  "the benchmark matches"
  GOOD: "INDEPENDENT comparison of the terminal reserve against the
         hand-derived net-premium closed form, relative difference < 1e-9"

A criterion that a TRANSPORT or ECHO comparison could satisfy is not an
acceptance criterion for a claim of correctness.
```

## Change 3 — Daily Dev: recorded comparisons name their producers

**Amend the step that records results into a ledger, session log or ADR.**

```
Any recorded comparison names WHAT PRODUCED EACH SIDE of every compared
quantity. A result is reported as agreement or parity only when the two
producers are independent; otherwise it is recorded as a harness check. A row
that cannot name two independent producers is a harness row, and saying so
costs nothing while mislabelling it costs a later session its premise.
```

## Change 4 — Daily Dev: epics owned by another routine

**Amend step 5b's "find the active Epic".**

```
EXCLUDE any epic owned by another routine when scanning for the active Epic —
currently docs/PLAN_mgcv_parity_engine.md / CONTINUATION_mgcv_parity_engine.md,
owned by the mgcv Parity routine, which has its own oracle setup and
convergence loop. Advancing it here would put two routines on one slice, with
two PRs against one CONTINUATION.

If an externally-owned epic is the ONLY IN PROGRESS continuation, treat the
Epic slot as EMPTY: follow the maintenance-mode path (a gated Tier-B/C pick
with its gate reason stated, or regenerate COMMERCIAL_VIABILITY_REVIEW),
rather than adopting it.
```

**Why this is needed now:** on `main` at 2026-08-16,
`CONTINUATION_mgcv_parity_engine.md` is the only genuinely IN PROGRESS
continuation — the others read COMPLETE, SLICES 1-5 DONE, and PARKED — and the
Tier-A ladder is exhausted per `COMMERCIAL_VIABILITY_REVIEW_2026-07-15.md`. So
step 5b's rule (a) lands on the parity epic by default.

### Where the boundary falls

The dividing question between the two routines is **not** which module the code
lives in. It is *what makes the work correct*:

| Correctness criterion | Owner |
|---|---|
| "matches the external reference implementation" | the parity routine — it has the oracle in the loop and cannot verify what it did not measure |
| internal: a closed form, an actuarial identity, a user-facing surface | daily dev |

A construction whose only definition of correct is "what the reference does"
cannot be built where the reference is unavailable. The exception is a genuine
handoff: once the reference's behaviour has been **measured and written down as
a derivation**, building against that written spec is ordinary feature work, and
daily dev can do it with the owning routine verifying afterwards.

---

## Applied changes, retained for the record

### Change 5 — PR Review: the provenance audit

```
VERIFICATION PROVENANCE (ADR-193, docs/VERIFICATION_STANDARD.md):

For EVERY comparison table in the PR — in the diff, the DEV_SESSION_LOG, the
PR body, a ledger, or a CI job summary:
  1. Name the two producers of each compared quantity. Write them down; do not
     accept the PR's own characterisation.
  2. Apply the mechanical test to the producing function's SIGNATURE: does it
     take the other side's payload as an input? Did our side supply the
     quantity to the reference?
  3. Classify: INDEPENDENT / ECHO / TRANSPORT.

Findings:
- A harness check reported as agreement or parity — in any of those places — or
  an acceptance criterion ticked on one, is a [P0].
- A new comparison whose producer carries no VerificationClaim is a [P1].
- A published table whose headline is hand-written rather than derived from
  evidence_markdown() is a [P1].
- A harness check HONESTLY labelled as ECHO/TRANSPORT is NOT a finding. Harness
  work is legitimate and often required first; the requirement is that it says
  so.

Do NOT approve a PR that reports a comparison as evidence of agreement without
naming two independent producers, even if every test passes and every number is
zero. Zeros are what a tautology looks like.
```

### Change 6 — PR Review: goldens are not correctness evidence

```
tests/qa/golden_outputs/ is this engine's own prior output. A passing golden
test means BEHAVIOUR HAS NOT CHANGED. It is never evidence that a number is
correct, and a PR body or session log citing goldens as validation of
correctness is a [P1] mischaracterisation.
```

### Change 7 — mgcv Parity: the provenance gate

Applied to the trigger prompt, and carried in `docs/ROUTINE_MGCV_PARITY.md`
step 5b so the authoritative file cannot supersede it. Adds the claim sentence,
the mechanical test, per-column classification, the note that tier and
provenance are different axes, a `feat(...)` vs `harness(...)` PR-title
convention, and a Provenance section in the session log.

---

## What is already done in the repo

| Piece | Where |
|---|---|
| The taxonomy, the guards, the derived headline | `src/polaris_re/core/verification.py` |
| The decision and its history | ADR-193, `docs/DECISIONS.md` |
| The project-wide rule, incl. the current-state audit | `docs/VERIFICATION_STANDARD.md` |
| Session reading list + `Never` entries | `CLAUDE.md` §10 |
| Review severity entries | `REVIEW.md` |
| Ledger provenance requirement | `docs/CONFORMANCE_LEDGER.md` preamble |
| The parity routine's own gate | `docs/ROUTINE_MGCV_PARITY.md` step 5b |
| Both Stage-A paths declaring provenance | `src/polaris_re/analytics/gam_stage_a.py` |
| CI job summary printing derived headlines | `.github/workflows/mgcv-conformance.yml` |
