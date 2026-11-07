# Session log 2026-10-22 — GAM dashboard epic start + D1

**Branch:** `claude/dreamy-galileo-0301r3`. **PR title:** `harness(mgcv-parity): D1 — HGAM fitter in the experience-improvement page (read-only), measured pre-run cost model` (no INDEPENDENT comparison lands; everything new is MEASUREMENT, own criterion).

## Oracle Version
Tier 1 only, local apt: R 4.3.3 / mgcv 1.9.1 (installed after `apt-get update`). Not used for any number: D1 reports no `mgcv` comparison. No tier-3 dispatch was needed. Pinned digest referenced by the unchanged parity evidence: `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`.

## Baseline (full suite, `pytest tests/ -m "not slow"`, before any change)
**5 failed, 4199 passed, 22 skipped, 145 deselected** — the same five table-dependent failures as the previous log (`test_loaded_ilec_feeds_tensor_mi_surface`, four `TestCalibratedPremiums`). (R was installed before this run; the R-gated end-to-end test is among the 22 skips or passes as the box allows.)

## Gap Before / Gap After
No parity gap in scope (not a parity slice). Before: no HGAM fit reachable from a page, no cost estimate. After: section on the page, model, 21 new tests passing.

## Provenance
- Page fits: `polaris_re.gam.gam` (already INDEPENDENT-verified, ADR-258/260/261). Not re-compared.
- Cost model leave-one-out: left = regression prediction (Polaris-recorded timings), right = the same recorded timings. **MEASUREMENT (own criterion)**, one machine. Not parity.
- Effect profiles: fit against itself, MEASUREMENT.
- Synthetic memory sweep: Polaris vs itself, Linux sandbox. MEASUREMENT.

## Hypotheses Tried
1. `log t ~ log rows` only: LOO worst factor 3.2, 93% within 3x (rejected: misses the pre-set tolerance).
2. `+ log coefficients`: worst 2.09, 15/15 within 3x (kept).
3. `+ log penalties`: worst 1.41 (not kept, the page cannot know penalties pre-run cheaply). Variants 1-3 were scored in one run; selecting 2 afterwards is disclosed in ADR-262.

## Findings
- Corrected the PLAN: R2 JSON does record Polaris `peak_rss_mb`, as a process high-water mark (upper bound only).
- Synthetic `gam` peak: 0.140/0.145/0.161 GB at 2k/10k/40k rows (18 coef).

## Box vs repo
The box names no slice; the repo's pointer named the epic start + D1. Followed the repo.

## Follow-ups
Maintainer run of predicted vs actual on one ILEC cell (CONTINUATION Q1). perf/history.jsonl row appended (the PR touches `src/polaris_re/` outside amendments 1-2's exemptions).

## After-change suite
`pytest tests/ -m "not slow"` with the 5 known table-dependent failures deselected (the whole `test_synthetic_block.py` file plus the one loader test): **4220 passed, 22 skipped, 150 deselected, 0 failed**. `pytest tests/qa/`: 85 passed, 9 skipped; goldens byte-identical (not edited). ruff format/check clean.

## Perf History
Row appended for commit `5b06d40`; creep verdict (PR review, `detect_creep` over 70 rows): no structural creep.

## Review round 1 (PR #277)
P1 harvest: PRODUCT_DIRECTION addendum 2026-10-22 added. P1 memory multiplier: the unmeasured 4x was replaced by a stated ASSUMPTION of 12x the floor (largest above-baseline ratio of the synthetic sweep at >=10k rows: 11.1x at 10k, 5.6x at 40k), printed in the warning text; the R2 per-cell ratios (5.6x-238x) are high-water confounded and not used. P2-1 signature now hashes the summed row hashes. P2-2 bam block uses estimate + LOO band; the 10.2 GB bound is a named constant. P2-3 `BAM_MEASURED` is now tested against the ADR-260 tables. P2-4 DoD line labelled MEASUREMENT in the PR body.

## Maintainer local-run finding (2026-11-07)
Uploading the T1_mid `cells.csv` (109,158 rows) stopped at the page's `q_base` validation and the GAM section never rendered: the section was placed after a check it does not need. Fixed: a frame missing the A/E columns now skips only the older diagnostics (warning) and still renders the HGAM section (`_missing_columns_fallback`; AppTest `test_frame_without_q_base_still_offers_the_gam_section`). The default formula names `death_count`, `attained_age`, `calendar_year`, `log_exposure`; a frame with other column names needs its own formula typed in.

## Tier-L batch (2026-11-07)
Six real-cell readings on the maintainer's M4 are recorded in `docs/CONTINUATION_gam_dashboard.md`: all inside the model's bands; MEASUREMENT, one machine. Follow-ups (slogdet warnings; per-fit gam RSS) are in the PRODUCT_DIRECTION addendum. CI on head 7e6e4b8 was fully green.

## Link handling fix (2026-11-07, review of PR #278's script)
`gam_dashboard_local_check.py::_spec` stripped the link from the family (`binomial(link="cloglog")` became `binomial`, i.e. logit) and silently ignored a weights column; the page's family list also had no link option. Fixed: the script keeps the full family string and refuses a spec with weights or an unsupported family; the page offers `binomial(link="cloglog")`. Tests: `test_cloglog_link_is_kept_end_to_end`, `test_cloglog_family_string_reaches_the_fit`. The cost model was not re-fitted (it never saw a cloglog cell: S1 was not fitted in R2).
