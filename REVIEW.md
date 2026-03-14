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

### P1 — Should fix before merge

- **Python 3.12 typing violations**: `Optional[X]` instead of `X | None`; `List[X]` instead
  of `list[X]`; `Dict[K, V]` instead of `dict[K, V]`; `Union[X, Y]` instead of `X | Y`;
  presence of `from __future__ import annotations` (never needed on 3.12)
- **Missing closed-form test**: any new actuarial calculation function without a corresponding
  test that verifies the result against a known closed-form solution
- **Wrong error type**: raising `ValueError` or `RuntimeError` directly instead of
  `PolarisValidationError` (business logic) or `PolarisComputationError` (numerical failure)
- **Array dtype omission**: `np.array(...)` without an explicit `dtype` argument

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
