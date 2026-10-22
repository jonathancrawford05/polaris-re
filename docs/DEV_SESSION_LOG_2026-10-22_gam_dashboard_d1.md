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
Maintainer run of predicted vs actual on one ILEC cell (CONTINUATION Q1). No perf/history.jsonl row: PR touches `src/polaris_re/` but adds only new modules outside the pricing perf closure — see below.
