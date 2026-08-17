# Verification standard — what counts as evidence

> **Scope: the whole project, not one epic.** Any time Polaris output is compared
> against a reference — `mgcv`, an AXIS/Prophet extract, a textbook closed form, a
> cedant's own figures, a prior version of this engine — this standard applies.
> Read it before writing a comparison, a conformance harness, or an acceptance
> criterion. The machinery is `polaris_re.core.verification`; the decision is
> ADR-193.

---

## 1. The problem this exists to stop

A comparison table of near-zero diffs looks the same in all three of these
situations:

| Relationship | What produced each side | What a zero diff proves |
|---|---|---|
| **INDEPENDENT** | Two implementations computed the quantity from the same *recipe*, neither reading the other's output | **Parity.** The only relationship that can produce a genuine disagreement |
| **ECHO** | One side supplied the quantity; the other returned it | The reference did not reparameterise, rescale or reorder what it was handed |
| **TRANSPORT** | One side computed it; the other parsed it | Serialisation and packaging work |

All three are worth running. Only the first is parity evidence.

The failure mode is not dishonesty. Twice in the `mgcv` parity epic the prose was
scrupulously accurate — the docstrings, the session logs and the ledger all said
"packaging, not verification" — and the mislabelling still propagated, because
**a caveat in a paragraph does not travel and a column of `0.000e+00` does.** It
travelled into the CI job summary, the ledger's "agrees" column, the PR
description, and an automated review that approved on it.

So the rule cannot be "write an honest caption." It has to be structural.

## 2. The two-producer rule

> **A comparison is parity evidence only if two independent producers computed
> the compared quantity from the same recipe.**

**The mechanical test — apply it to the function signature, before reading a line
of the body:**

> If the function producing one operand takes the other side's payload as an
> input, it is not an independent producer.

`extract_smooth_terms(terms, r_terms)` fails on sight: `r_terms` *is* the other
operand. No amount of correct code inside changes that. Equally, if your side
*supplied* the quantity to the reference (as the `raw`/`paraPen` path supplies
`X` and `S` to `mgcv`), reading it back is ECHO, not parity.

Provenance is **per-quantity**, not per-comparison. One table may legitimately
carry an INDEPENDENT column beside ECHO ones — the `raw` path's `rank` is
computed by `numpy.linalg.matrix_rank` on one side and `mgcv`'s own rank
determination on the other, while `X` and `S` in the same table are echoed. Say
so per column; do not average it into one verdict.

## 3. What you must do

### 3.1 Declare provenance in the type, at the producer

Every producer of a comparison operand declares a
`VerificationClaim` — the claim sentence plus one `ComparedQuantity` per column,
each naming both producers. Declaring is not optional: carry the claim on the
artefact the producer returns, with **no default**, so a new producer cannot be
written without answering the question.

```python
from polaris_re.core.verification import (
    ComparedQuantity, ComparisonProvenance, VerificationClaim,
)

MY_CLAIM = VerificationClaim(
    claim="polaris_re builds the cr basis from the knots; mgcv builds it via "
          "smoothCon(); compared on design_X and penalty_S.",
    quantities=(
        ComparedQuantity(
            quantity="design_X",
            left_producer="polaris_re.analytics.<the Python basis>",
            right_producer="mgcv smoothCon(..., absorb.cons=TRUE)$X",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
```

`ComparedQuantity` refuses, at construction, the declaration that is
self-evidently wrong: naming the **same producer on both sides** while claiming
`INDEPENDENT`.

### 3.2 Write the claim sentence *before* the code

Fill this in at authoring time — in the work order, the PLAN slice, or the ADR:

> *`<left>` computes `<quantity>` from `<recipe>`; `<right>` computes it via
> `<call>`; compared on `<columns>`.*

**If you cannot fill it in with two distinct computations, you are building a
harness slice, and its title must say so.** That is a legitimate and often
necessary thing to build — slices 1 and 1b both were — but it is not parity, and
naming it honestly up front is what stops it being reported as parity later.

### 3.3 Never hand-write the headline of a published table

Report generators call `evidence_markdown(claim)` and print it **above** the
diffs. The headline is *derived* from the declared provenance:

- all columns independent → `**Parity comparison** — …`
- some independent → `**Harness check with one parity column — NOT basis parity.** …`
- none independent → `**Harness check — NOT parity.** …`

A human writing that line by hand is exactly the step that failed before.

### 3.4 Gate parity claims with `require_parity_evidence`

Wherever a parity claim is *asserted* — an acceptance check, a CI gate, a report
that prints the word "parity" — pass the cited quantities through
`require_parity_evidence(...)`. It raises `PolarisValidationError` naming each
quantity that is not independently produced. A harness result then cannot
silently satisfy a parity gate.

### 3.5 Write acceptance criteria that a harness cannot satisfy

| ❌ Not checkable | ✅ Checkable |
|---|---|
| "Stage A exact" | "**INDEPENDENT** Stage-A comparison exact for `bs="cr"`: Python's `cr` basis vs `smoothCon()$X`, `max_abs_design_diff < 1e-9`" |
| "The comparator agrees" | "`rank` (INDEPENDENT) agrees; `X`/`S` (ECHO) confirm no reparameterisation" |

Name the provenance in the criterion. A slice that ships only transport then
cannot tick its own box.

### 3.6 Record provenance in the ledger

Every new row of `docs/CONFORMANCE_LEDGER.md` states, in its metric column, what
produced each side and the provenance of each compared quantity. A row that
cannot name two producers is a harness row and its verdict says
`CONFIRMED (harness)`, never `CONFIRMED (parity)`.

## 4. What review checks

The PR review routine (and any human reviewer) applies this to **every diff table
in the PR**:

1. Name the two producers of each compared quantity.
2. If they are the same producer, or one reads the other's output, the table is a
   harness check.
3. A harness check reported as parity — in the PR body, the session log, the
   ledger, a CI summary, or an acceptance criterion — is a **[P0]**.
4. A comparison shipped with no declared `VerificationClaim` is a **[P1]**.

## 5. Where the project stands (2026-08-16)

Applying the standard to the `mgcv` parity epic, honestly:

| Comparison | Provenance | Status |
|---|---|---|
| Conformance levels 1–5 (`eta`, coefficients, `edf`/`tr(F)`, `Vb`, selected λ) | **INDEPENDENT** — two separately implemented fitters over a shared `(X, S)` | Real parity evidence. This is why level 4 can genuinely *disagree* (ADR-190) |
| Stage A, `raw`/`paraPen` path — `X`, `S` | ECHO — Python supplies them, mgcv is fitted on them | No-tampering check (slice 1) |
| Stage A, `raw`/`paraPen` path — `rank` | **INDEPENDENT** — `numpy` vs `mgcv`'s rank determination | The one parity column Stage A has today |
| Stage A, mgcv-native path — all columns | TRANSPORT — one producer, parsed by the other | Round-trip check (slice 1b) |
| R-side internal guard (`smoothCon` vs `lpmatrix`/`m$smooth[[j]]`) | **INDEPENDENT**, entirely inside R | Real evidence about mgcv, none about Polaris |

**The engine's *fitter* has genuine parity evidence; its *bases* have none yet.**
Slice 2 — a Python `cr` basis built from knots and Wood's definition, compared
against `smoothCon()$X`/`$S` — is the first Stage-A work that can carry
INDEPENDENT provenance, and the first that may be reported as basis parity.

## 6. Applying this outside the mgcv epic

The same three questions apply to every comparison the project makes:

- **Closed-form validation packs** — the closed form is an independent producer
  (hand-derived, not read from the engine), so these are INDEPENDENT. Keep them
  that way: a "closed form" computed by calling the function under test is
  circular.
- **Golden regression** (`tests/qa/golden_outputs/`) — goldens are *this
  engine's own prior output*. They are a **regression** check (has behaviour
  changed?), never correctness evidence, and must never be cited as validation
  that a number is right.
- **Cedant / vendor reconciliation** — genuinely INDEPENDENT, and the highest-value
  evidence the project can obtain. Declare it as such.
- **Any future reference implementation** — apply §2 before writing the harness.
