# The `mgcv` conformance ledger

Append-only, one row per hypothesis tried (`docs/ROUTINE_MGCV_PARITY.md`). The `tier +
digest` column is not bookkeeping: without it, a row measured on local apt R and a row
measured on the pinned image read identically, and the ledger's whole purpose —
stopping session N+3 from re-running session N's dead end — depends on a later reader
being able to tell whether a "no movement" verdict was a real result or a tier-1
artefact.

| date | slice | hypothesis | the one change | metric | before | after | tier + digest | verdict |
|---|---|---|---|---|---|---|---|---|
| 2026-08-15 | 1 | `predict(gam(...), type="lpmatrix")`'s smooth-term block and `smoothCon(s(x, bs="cr"), absorb.cons=TRUE)$X` are the SAME object (PLAN §5 risk 1), not two competing Stage-A referents | added `scripts/smoothcon_lpmatrix_probe.R`, ran it against a fresh `bs="cr"` case (no exchange dependency) | `max_abs_diff_lpmatrix_vs_smoothcon_x`, `max_abs_diff_gam_smooth_S_vs_smoothcon_S` | n/a (first measurement) | **0.0 exactly**, 3 cases (k=8 default knots, k=13 default knots, k=8 supplied knots) | tier 1, R 4.3.3 / mgcv 1.9.1 (local apt) — **pending tier-3 re-run on the pinned oracle before this may be treated as settled** | HYPOTHESIS, awaiting tier-3 confirmation before it enters CONTINUATION/DECISIONS |
