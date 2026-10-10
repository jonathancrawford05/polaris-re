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
| **R3** | scale: exact speedups or `bam`/`discrete=TRUE`, decided by R2's profile and the time budget | NOT STARTED (gated on R2) |
| **R4** | `tp` (L7); bare `s(x)` accepted | NOT STARTED (any time after R1) |

## Maintainer questions (recommended answers in PLAN §6)
- **Q-R2a** trial formulas T1-T3 and the ILEC covariate mapping.
- **Q-R2b** the time budget for the T3-size fit (R3's branch point). Please set before R2 runs.
- **Q-R2c** what derived scalars may be committed from ILEC runs under `DATA_LICENSING.md` §5a.
- **Q-R2d** the three aggregation granularities.
- **Q-order** R3 before R4, or the reverse.

## Carried over (not part of this epic's slices)
- Parity-engine Slice 10 is DONE as a finding (ADR-256); its standing limitations apply to any *pivoted* fit.
- `PLAN_mgcv_capability_ladder.md`: 6b is superseded for `select=TRUE` on `cr+re+ti` (already supported); its residual is R1. `sz` free-`sp` (L11) is parked. L6 `fs`, L8 `te`/`t2` stay behind this epic.
- Pricing / CLI / dashboard / MCP wiring stays unmade (Anchor 7) until R2 and, if triggered, R3 are recorded.
