# The `mgcv` conformance ledger

Append-only, one row per hypothesis tried (`docs/ROUTINE_MGCV_PARITY.md`). The `tier +
digest` column is not bookkeeping: without it, a row measured on local apt R and a row
measured on the pinned image read identically, and the ledger's whole purpose —
stopping session N+3 from re-running session N's dead end — depends on a later reader
being able to tell whether a "no movement" verdict was a real result or a tier-1
artefact.

| date | slice | hypothesis | the one change | metric | before | after | tier + digest | verdict |
|---|---|---|---|---|---|---|---|---|
| 2026-08-15 | 1 | `predict(gam(...), type="lpmatrix")`'s smooth-term block and `smoothCon(s(x, bs="cr"), absorb.cons=TRUE)$X` are the SAME object (PLAN §5 risk 1), not two competing Stage-A referents | added `scripts/smoothcon_lpmatrix_probe.R`, ran it against a fresh `bs="cr"` case (no exchange dependency) | `max_abs_diff_lpmatrix_vs_smoothcon_x`, `max_abs_diff_gam_smooth_S_vs_smoothcon_S` | n/a (first measurement) | **0.0 exactly**, 3 cases (k=8 default knots, k=13 default knots, k=8 supplied knots) | tier 1, R 4.3.3 / mgcv 1.9.1 (local apt) | HYPOTHESIS — confirmed below |
| 2026-08-15 | 1 | same hypothesis, re-measured on the authoritative oracle per `ROUTINE_MGCV_PARITY.md` step 2 (a tier-1 structural claim about which mgcv function calls which is exactly the "version change is different code" case the routine names) | none — same probe, dispatched via CI `workflow_dispatch` on `173d186` | same two metrics | tier-1 reading above | **0.0 exactly**, all 3 cases, identical to the tier-1 reading at every printed digit | **tier 3**, R 4.6.1 / mgcv 1.9.4, oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8` (build 8), run [31907362222](https://github.com/jonathancrawford05/polaris-re/actions/runs/31907362222) | **CONFIRMED — settled.** `smoothCon(absorb.cons=TRUE)` is Stage A's referent; recorded in `CONTINUATION_mgcv_parity_engine.md`. Required levels 1-3 of the existing suite also still agree on this run — no regression from the CI workflow edit. |

