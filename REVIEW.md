# REVIEW.md — Polaris RE Code Review Instructions

> This file provides instructions specifically for automated code review (GitHub Actions,
> Claude Code Review). It complements `CLAUDE.md`, which governs interactive coding sessions.
> Do not duplicate content from `CLAUDE.md` here — this file is review-specific guidance only.

---

## Review Priorities

Reviews should focus exclusively on issues that could cause **incorrect actuarial results,
runtime failures, or degraded code quality**. Do not comment on style issues enforced by Ruff.

### P0 — Block-level issues (must fix before merge)

- **Actuarial calculation errors**: incorrect NAR formula, wrong discount factor application,
  off-by-one in projection time steps, incorrect select/ultimate table lookup logic
- **Vectorisation violations**: any Python loop iterating over policies or projection periods
  where a NumPy vectorised operation should be used instead
- **Pydantic contract bypass**: passing raw `dict` where a `PolarisBaseModel` subclass is
  required; missing `Field(description=...)` on model fields; using `model.dict()` instead
  of `model.model_dump()` (Pydantic v2 API)
- **Float equality comparisons**: using `==` on floats — must use `np.testing.assert_allclose`
  in tests and appropriate tolerances in production code
- **Silent exception suppression**: bare `except:` or `except Exception: pass` blocks
- **Hardcoded assumption values**: mortality rates, lapse rates, or discount rates embedded
  as literals in product or treaty code rather than passed via `AssumptionSet`
- **A harness check reported as parity evidence** (ADR-193,
  `docs/VERIFICATION_STANDARD.md`): for **every** comparison table in the PR — in the
  diff, the session log, the PR body, the conformance ledger or a CI job summary — name
  the two producers of each compared quantity. If they are the same producer, or one
  reads the other's output (the mechanical test: *the function producing one operand
  takes the other side's payload as an input*), the table is a harness check. Reporting
  it as parity/agreement, or ticking an acceptance criterion on it, is a P0. Reporting it
  honestly as ECHO/TRANSPORT is fine and often expected — harness slices are legitimate
  work.

### P1 — Should fix before merge

- **Python 3.12 typing violations**: `Optional[X]` instead of `X | None`; `List[X]` instead
  of `list[X]`; `Dict[K, V]` instead of `dict[K, V]`; `Union[X, Y]` instead of `X | Y`;
  presence of `from __future__ import annotations` (never needed on 3.12)
- **Missing closed-form test**: any new actuarial calculation function without a corresponding
  test that verifies the result against a known closed-form solution
- **Wrong error type**: raising `ValueError` or `RuntimeError` directly instead of
  `PolarisValidationError` (business logic) or `PolarisComputationError` (numerical failure)
- **Array dtype omission**: `np.array(...)` without an explicit `dtype` argument
- **Undeclared comparison provenance**: a new comparison whose producer does not carry a
  `VerificationClaim` (`polaris_re.core.verification`), or a published table whose
  headline is hand-written rather than derived via `evidence_markdown()`
- **A parity acceptance criterion with no provenance named**: "Stage A exact" rather than
  "**INDEPENDENT** Stage-A comparison exact for `bs="cr"`" — a criterion a harness slice
  could tick

### P2 — Suggestions (optional, non-blocking)

- Opportunities to improve test parametrisation
- Naming inconsistencies with actuarial notation conventions (see CLAUDE.md §5)
- Missing module-level docstrings on new files

---

## What to Ignore

Do not comment on:
- Import ordering — Ruff `I` ruleset handles this automatically
- Line length — Ruff `E501` handles this
- Whitespace or blank line counts
- Docstring formatting (Google vs NumPy style debates)
- Minor variable naming that does not conflict with actuarial notation

---

## Severity Notation

Use this format when reporting findings so they are easy to triage:

```
**[P0 - Actuarial Error]** `src/polaris_re/products/term_life.py:84`
Description of the issue and why it matters.
Suggested fix or approach.
```

---

## Phase Awareness

Polaris RE is currently in **Phase 1 MVP**. Out-of-scope items (UL account value, Modco,
Monte Carlo UQ, experience studies, CLI) should not be flagged as missing. Refer to
`docs/ROADMAP.md` for the current phase scope if uncertain whether a component is expected.
