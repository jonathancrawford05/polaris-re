# Continuation: GAM in the dashboard

**Plan:** `docs/PLAN_gam_dashboard.md` · **ADR:** ADR-262 · **Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Created:** 2026-10-22 (epic start + D1 in one session, as the pointer directed).
**Status:** **IN PROGRESS. D1 IMPLEMENTED 2026-10-22, awaiting merge and the maintainer's use of it.** D2 and D3 are not started; release conditions in the PLAN §4.

| slice | status |
|---|---|
| D1 fit and display, read-only | implemented (ADR-262): section in the experience-improvement page; cost model `polaris_re.gam.cost_model`; tests `tests/test_gam/test_cost_model.py`, `tests/test_dashboard/test_gam_fit_section.py` |
| D2 fit as input to A/E / improvement views | NOT STARTED. Release: the maintainer's use of D1 and a written go |
| D3 CLI / MCP / API | NOT STARTED. Release: written go after D2 |

## Maintainer questions
1. **Maintainer run of the cost model.** The model is fitted on your M4 timings, but nothing has confirmed its predictions on a fresh fit there. *Recommended:* run the page on one ILEC `mid` cell with each engine and tell me predicted vs actual; I would record it (tier L) and widen the band if it misses.
2. **Profiles vs partial effects.** D1 shows link profiles with others held at median/reference. *Recommended:* keep for D1; decide partial effects (and `ti`/`by` terms) when you specify D2.
3. **Corrected fact:** R2 did record `gam` peak RSS, but only as a process high-water (upper bound). See ADR-262.

## Open limits
`estimate_n_coef` is checked on one synthetic fit only. The sandbox memory sweep is off-range. `bam` has no `summary()` / `reml_score`.
