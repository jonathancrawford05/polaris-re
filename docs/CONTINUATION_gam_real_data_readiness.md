# Continuation: GAM real-data readiness

**Plan:** `docs/PLAN_gam_real_data_readiness.md`
**Routine:** `docs/ROUTINE_MGCV_PARITY.md` (plus the maintainer-run step protocol, PLAN §3)
**Created:** 2026-10-10, plan-writing session (ADR-257).
**Status:** **PROPOSED -> ACTIVE on merge. No slice started.** Next session takes **Slice R1** (`select=TRUE` with factor-`by`): write the claim sentence and the R1-a..d predictions' tier-1 reading first (`unidentified_directions` under `select=TRUE`; the stability probe extended to these cells), then the capability.

## Slice status

| slice | scope | status |
|---|---|---|
| **R1** | `select=TRUE` + factor-`by` (both forms, four families); `mgcv` stability probe first | NOT STARTED |
| **R2** | ILEC trial + performance profile; routine builds the harness/runbook, maintainer + Cowork run it | NOT STARTED (release: R1 code merged) |
| **R4** | `tp` (L7); bare `s(x)` accepted | NOT STARTED (executes after R2) |
| **R3** | scale: exact speedups or `bam`/`discrete=TRUE`, decided by R2's profile and the 10-minute ceiling | NOT STARTED (executes after R4; only if the 10-minute ceiling is exceeded or the ratio is above 1.5) |

## Maintainer questions
**Answered 2026-10-10 (PR #265 review):** Q-R2a (T1-T3 with changes: three smoker levels, `U` kept, Poisson+offset primary, S1-S3 sensitivities), Q-R2b (10-minute ceiling, Polaris fit only, fixed reference machine, ratio against `mgcv::gam`), Q-R2c (timings, sizes, agreement differences; no coefficients or contrasts), Q-R2d (`full` = the banded run's key set), Q-order (R1, R2, R4; R3 only if needed).
**Q-R2b2 answered (2026-10-10): report the Polaris/`mgcv::gam` ratio; above 1.5 requires investigating `bam`.**
**Open (recommended answers in PLAN §6):** **Q-R2b2 confirmation** (applies to T1-T3 at `full` granularity only); **Q-R2e** confirm `max |Δeta| / se.fit <= 0.1` as the scale-aware criterion. **Q-R2f answered (2026-10-10): the maintainer's current MacBook is the reference machine** (PLAN R2 records the emulation and thermal fairness rules).

## Carried over (not part of this epic's slices)
- Parity-engine Slice 10 is DONE as a finding (ADR-256); its standing limitations apply to any *pivoted* fit.
- `PLAN_mgcv_capability_ladder.md`: 6b is superseded for `select=TRUE` on `cr+re+ti` (already supported); its residual is R1. `sz` free-`sp` (L11) is parked. L6 `fs`, L8 `te`/`t2` stay behind this epic.
- Pricing / CLI / dashboard / MCP wiring stays unmade (Anchor 7) until R2 and, if triggered, R3 are recorded.
