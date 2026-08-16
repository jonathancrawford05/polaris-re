# Proposed Changes — Daily Dev + PR Review routines (2026-08-16)

## Why

The `mgcv` parity epic exists to prove this engine reproduces `mgcv`. Two
consecutive slices shipped comparison tables that could not, structurally,
demonstrate that — and the second of those slices had been carved out
specifically to repair the first one's incomplete verification:

- **Slice 1** (`raw`/`paraPen`): Python builds `X` and `S`, hands them to `mgcv`,
  and reads them back. A zero diff proves no reparameterisation, not basis
  parity. Only `rank` is independently produced.
- **Slice 1b** (mgcv-native): `extract_smooth_terms` parses the R payload and is
  then compared against that same payload. Structurally zero.

Nothing was misstated at any point. Every docstring, session log and ledger row
said "packaging, not verification." **The caveat did not travel; the zeros did**
— into the CI job summary, the ledger's "agrees" column, the PR body, and an
automated review that approved on it.

ADR-193 and `docs/VERIFICATION_STANDARD.md` fix this in the codebase (provenance
declared in the type, headlines derived from the declaration, a
`require_parity_evidence` gate). The routines themselves need the matching edits,
because the routine prompts live in the trigger configuration **outside this
repo** — the human who owns those triggers must apply what follows. This PR
changes only the code and the docs.

These edits are deliberately written to generalise: they say "any reference
implementation," not "mgcv," so they bind future comparison work against vendor
extracts, cedant data, closed forms, or a future replacement engine.

---

## Change 1 — Daily Dev: a verification-provenance step

**Insert as a new step immediately before the quality gate (currently step 4).**

```
== VERIFICATION PROVENANCE (any work that compares against a reference) ==

If this session's work compares Polaris output against ANY reference
implementation — mgcv, a vendor extract (AXIS/Prophet), a cedant's own
figures, a textbook closed form, a prior engine version — then BEFORE
writing the comparison:

a. Read docs/VERIFICATION_STANDARD.md.

b. Write the claim sentence, in the work order / PLAN slice / ADR:
     "<left> computes <quantity> from <recipe>; <right> computes it via
      <call>; compared on <columns>."
   If you cannot fill it in with two DISTINCT computations, this is a
   HARNESS slice. That is legitimate work — say so in its title and in the
   PR title, and do not report it as parity.

c. Apply the mechanical test to the producer's SIGNATURE, before its body:
   if the function producing one operand takes the other side's payload as
   an input, it is not an independent producer. Likewise, if your side
   SUPPLIED the quantity to the reference, reading it back is ECHO.

d. Declare provenance in the type: every producer carries a
   VerificationClaim (polaris_re.core.verification) with one
   ComparedQuantity per column, each naming both producers. Provenance is
   PER-QUANTITY — a table may carry an INDEPENDENT column beside ECHO ones.

e. Never hand-write the headline of a published comparison table. Call
   evidence_markdown(claim) and print it above the diffs.

f. Gate any asserted parity claim with require_parity_evidence(...).
```

## Change 2 — Daily Dev: acceptance criteria must name provenance

**Amend the work-order / PLAN authoring step.**

```
Any acceptance criterion about agreement with a reference must name the
provenance it requires, so a harness slice cannot tick a parity box:

  BAD:  "Stage A exact"
  GOOD: "INDEPENDENT Stage-A comparison exact for bs='cr': Python's cr
         basis vs smoothCon()$X, max_abs_design_diff < 1e-9"

A criterion that a TRANSPORT or ECHO comparison could satisfy is not an
acceptance criterion for a parity claim.
```

## Change 3 — Daily Dev: ledger rows carry producers

**Amend the conformance-ledger step.**

```
Every new ledger row names, in its metric column, WHAT PRODUCED EACH SIDE of
every compared quantity. The verdict reads CONFIRMED (parity) only when the
two producers are independent; otherwise CONFIRMED (harness). A row that
cannot name two independent producers is a harness row.
```

## Change 4 — PR Review: the provenance audit

**Insert into the CODE REVIEW step, under ACTUARIAL CORRECTNESS.**

```
VERIFICATION PROVENANCE (ADR-193, docs/VERIFICATION_STANDARD.md):

For EVERY comparison table in the PR — in the diff, the DEV_SESSION_LOG, the
PR body, the conformance ledger, or a CI job summary — do this explicitly:

1. Name the two producers of each compared quantity. Write them down; do
   not accept the PR's own characterisation.
2. Apply the mechanical test to the producing function's SIGNATURE: does it
   take the other side's payload as an input? Did our side supply the
   quantity to the reference?
3. Classify: INDEPENDENT (parity evidence) / ECHO (no-tampering) /
   TRANSPORT (round trip).

Findings:
- A harness check (ECHO/TRANSPORT) reported as parity or agreement — in any
  of those places — or an acceptance criterion ticked on one, is a [P0].
- A new comparison whose producer carries no VerificationClaim is a [P1].
- A published table whose headline is hand-written rather than derived from
  evidence_markdown() is a [P1].
- A harness slice HONESTLY labelled as ECHO/TRANSPORT is NOT a finding.
  Harness work is legitimate and often required first (Anchor 1's "prove the
  harness on a known-good basis"); the requirement is that it says so.

Do NOT approve a PR that reports a comparison as parity evidence without
naming two independent producers, even if every test passes and every number
is zero. Zeros are what a tautology looks like.
```

## Change 5 — PR Review: goldens are not correctness evidence

**Amend the golden-regression step.**

```
tests/qa/golden_outputs/ is this engine's own prior output. A passing golden
test means BEHAVIOUR HAS NOT CHANGED. It is never evidence that a number is
correct, and a PR body or session log citing goldens as validation of
correctness is a [P1] mischaracterisation.
```

---

## What is already done in the repo (this PR)

| Piece | Where |
|---|---|
| The taxonomy, the guards, the derived headline | `src/polaris_re/core/verification.py` |
| The decision and its history | ADR-193, `docs/DECISIONS.md` |
| The project-wide rule, incl. the current-state audit | `docs/VERIFICATION_STANDARD.md` |
| Session reading list + `Never` entries | `CLAUDE.md` §10 |
| Review severity entries | `REVIEW.md` |
| Ledger provenance requirement | `docs/CONFORMANCE_LEDGER.md` preamble |
| Both Stage-A paths declaring provenance | `src/polaris_re/analytics/gam_stage_a.py` |
| CI job summary printing derived headlines | `.github/workflows/mgcv-conformance.yml` |
| Slice 2's rewritten acceptance criteria | `docs/PLAN_mgcv_parity_engine.md` |

Only the five routine-prompt edits above remain, and they are the human trigger
owner's to apply.
