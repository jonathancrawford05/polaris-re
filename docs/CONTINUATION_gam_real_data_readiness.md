# Continuation: GAM real-data readiness

**Plan:** `docs/PLAN_gam_real_data_readiness.md`
**Routine:** `docs/ROUTINE_MGCV_PARITY.md` (plus the maintainer-run step protocol, PLAN §3)
**Created:** 2026-10-10, plan-writing session (ADR-257).
**Status:** **IN PROGRESS. Slice R1 DONE 2026-10-11 (ADR-258, tier 3 runs 38081942434 / 38102487555; PR #266 accepted by the maintainer for merge).** The solver findings for the refused shapes are in `docs/FINDINGS_select_factor_by_outer_search.md`. Next session takes **Slice R2** (the ILEC trial harness, runbook and whitelist test; ends WAITING ON MAINTAINER RUN) once R1's code is merged.

## Slice status

| slice | scope | status |
|---|---|---|
| **R1** | `select=TRUE` + factor-`by` (both forms, four families); `mgcv` stability probe first | **DONE** (ADR-258): `f + s(x,by=f)` and `s(x,by=f)` accepted, 60/60 draws agree; bare-smooth-beside-`by` forms refused by name (8/60 draws disagree, class iii) |
| **R2** | ILEC trial + performance profile; routine builds the harness/runbook, maintainer + Cowork run it | NOT STARTED (release: R1 code merged) |
| **R4** | `tp` (L7); bare `s(x)` accepted | NOT STARTED (executes after R2) |
| **R3** | scale: exact speedups or `bam`/`discrete=TRUE`, decided by R2's profile and the 10-minute ceiling | NOT STARTED (executes after R4; only if the 10-minute ceiling is exceeded or the ratio is above 1.5) |

## Maintainer questions
**Q-R1b ANSWERED 2026-10-11 (maintainer, PR #266): accept the allowlist (bare `s(x)`, a second factor-`by`, and `ti(x,z)` beside a factor `by` refused; numeric `by` accepted), provided the findings are documented for later solver work — done (`docs/FINDINGS_select_factor_by_outer_search.md`). The `ti` refusal rests on 1 miss in 60 and is the first candidate to lift when more draws or a tie-breaking rule exist.**
**Q-R1 ANSWERED 2026-10-10 (maintainer, PR #266): keep the narrower refusal.** R1-d said a non-converging block means "keep refusing that construct". The measured failure is narrower than the old blanket refusal: only the forms with a bare `s(x)` beside `s(x,by=f)` disagree (8/60), the other two forms agree 60/60. I lifted the refusal for the latter and kept it (by name) for the former. *Recommended:* accept this reading. If you meant the blanket refusal to stay, revert the single check in `gam()` (`_build_model`) and the two forms move back to the refusal table.
**Answered 2026-10-10 (PR #265 review):** Q-R2a (T1-T3 with changes: three smoker levels, `U` kept, Poisson+offset primary, S1-S3 sensitivities), Q-R2b (10-minute ceiling, Polaris fit only, fixed reference machine, ratio against `mgcv::gam`), Q-R2c (timings, sizes, agreement differences; no coefficients or contrasts), Q-R2d (`full` = the banded run's key set), Q-order (R1, R2, R4; R3 only if needed).
**Q-R2b2 answered (2026-10-10): report the Polaris/`mgcv::gam` ratio; above 1.5 requires investigating `bam`.**
**Open (recommended answers in PLAN §6):** **Q-R2b2 confirmation** (applies to T1-T3 at `full` granularity only); **Q-R2e answered (2026-10-10): gate `max |Δeta| / se.fit` at 0.1, flag above 0.01.** **Q-R2f answered (2026-10-10): the maintainer's current MacBook is the reference machine** (PLAN R2 records the emulation and thermal fairness rules).

## Carried over (not part of this epic's slices)
- Parity-engine Slice 10 is DONE as a finding (ADR-256); its standing limitations apply to any *pivoted* fit.
- `PLAN_mgcv_capability_ladder.md`: 6b is superseded for `select=TRUE` on `cr+re+ti` (already supported); its residual is R1. `sz` free-`sp` (L11) is parked. L6 `fs`, L8 `te`/`t2` stay behind this epic.
- Pricing / CLI / dashboard / MCP wiring stays unmade (Anchor 7) until R2 and, if triggered, R3 are recorded.
