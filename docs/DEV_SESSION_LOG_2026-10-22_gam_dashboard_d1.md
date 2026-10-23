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
