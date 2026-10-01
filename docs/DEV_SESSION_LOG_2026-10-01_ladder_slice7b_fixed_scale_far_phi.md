# Dev session log — 2026-10-01 — ladder slice 7b: fixed-scale quasi-Poisson, far-phi basin

**Branch:** `claude/intelligent-hamilton-114ssh` (draft PR). **PR title class:** `feat(mgcv-parity)` — lands an INDEPENDENT comparison that now AGREES at both phi.

## Claim sentence (written before the code)
Polaris's `fit_polaris_gam` (`poisson(log)`, `gamma=phi`) selects its own four `log10(lambda)` from two starts (bounds-centre; the `gamma=1` solution), keeping the lower own-criterion score; `mgcv` computes it via `gam(quasipoisson(log), method="REML", scale=phi)`; compared at phi in {2,6} on `eta`, `edf_total` (ADR-221 gate), `log10(sp)`, per-term edf (reported).

## Routine notes
Box and ROUTINE file agree on fact; the box's "CURRENT STATE" pointed at ADR-207; the CONTINUATION shows the live frontier is the capability-ladder epic (ladder slice 7b), per the work-selection rule. Trimming the box is a maintainer edit.

## Oracle Version
Tier 1: R 4.3.3 / mgcv 1.9.1 (apt; unchanged). Tier 2: unavailable (no daemon checked). Tier 3: R 4.6.1 / mgcv 1.9.4, `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`, run 36903733782 (head `2ccf4cb`).

## Baseline
`make test`: 3826 passed, 3 skipped (R installed; mortality tables converted first). No failures.

## Gap Before (tier 1 and tier 3 identical in verdict, ADR-236)
phi=6: `eta` 0.2841, `edf_total` -2.1797 (tier 3). phi=2 agrees.

## Hypotheses Tried
1. *Seeding the search at a nearby solution reaches mgcv's basin.* Seed from phi=2's solution: `eta` 1.5e-05 (tier 1). HELD, but "phi=2" is an arbitrary seed.
2. *Continuation from `gamma=1` (natural scale): single jump or ladder of gammas (x2, x1.5).* Jump and both ladders reach the basin on the pinned fixture. On other draws (seeds 11, 22; phi 3, 8): a bare jump was worse than cold on one cell (seed 11, phi=8: 0.0257 vs 0.0153; gate 2e-2); ladders gave no consistent benefit and add a tuned ratio. Not adopted.
3. *Keep the lower own-criterion score of {cold, jump}.* Picked the mgcv-nearer fit in all 6 tier-1 cells. ADOPTED. One change to the search; no tolerance, no tuned constant.
Tier 3: phi=6 `eta` 6.678e-05, `edf_total` -0.0010.

## Gap After (tier 3)
phi=2: `eta` 2.607e-06, `edf_total` +0.0001. phi=6: `eta` 6.678e-05, `edf_total` -0.0010, `log10(sp)` diff 0.0004, agrees. Score @ Polaris/mgcv sp 204.2549/204.2549.

## Provenance
| column | left | right | class |
|---|---|---|---|
| `eta` | `fit_polaris_gam` at its own selected lambda | `m$linear.predictors` of `quasipoisson(scale=phi)` | INDEPENDENT |
| `log10(sp)` | Polaris search | `log10(m$sp)` | INDEPENDENT (reported, not gated) |
| `edf_total`/per-term edf | `PolarisGAMFit` | `sum(m$edf)`/`s.table` | INDEPENDENT |
| `phi` | supplied to both | supplied to both | input |
| score table | Polaris criterion at both sp | (mgcv sp is a scorer input) | DIAGNOSTIC |
Start selection reads Polaris's own `reml_score` only; recipe-typed signature + hostile-plant test unchanged.

## Caveats
Conformance-only change; production `fit_polaris_gam` unchanged (slice 7c registered). The extra draws (phi=8) have mgcv sp at ~1e10 corners — weak evidence about generality. Tier-1 extra draws are hypotheses, not committed numbers.

## Gate
`continue-on-error` removed; new step gates `eta`/`edf_total` at every phi, missing JSON fails. (Option C.)

## Quality gate / perf
ruff clean; targeted tests 9 passed including slow R round trip asserting phi=6. No `perf/history.jsonl` row: only a `*_conformance.py` module outside the probe closure changed (ADR-177 amendment 2).

## Follow-ups
Slice 7c (registered in PLAN). Slice 3c unblocked.
