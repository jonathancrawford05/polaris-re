# Session log — 2026-08-31 — Slice 5f: multi-start on a covariate-SHARING N=8 structure

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 5f — `docs/PLAN_mgcv_parity_engine.md`, registered 2026-08-30 (ADR-213).
The routine's "next unchecked slice" rule selected it (slice 5f precedes slice 6
in the PLAN's own ordering; both were READY, but 5f was registered first — the
identical reasoning that selected 5e over 6 the session before).
**PR:** this branch (`claude/intelligent-hamilton-u2qecs`), draft.
**ADR:** ADR-214.

## Setup

- `uv sync --all-extras` — clean.
- Installed the local scratch oracle (tier 1): `apt-get install -y -qq
  r-base-core r-cran-mgcv r-cran-jsonlite` failed on stale package-index
  404s first (the same recurring transient prior sessions record —
  `docs/DEV_SESSION_LOG_2026-08-30_mgcv_parity_slice5e_multistart.md`
  hit the identical failure); `apt-get update` fixed it. Versions
  recorded: **R 4.3.3 / mgcv 1.9.1 / jsonlite 1.8.8** — matches the
  routine's expected apt versions exactly, no drift to flag. (Tier 1 is
  not used for any quantity in this session's own measurement — see
  "No mgcv comparison" below; installed per the routine's own SETUP step
  2, unconditionally.)
- `OPENBLAS_NUM_THREADS` is not exported for a fixed baseline run; the
  slice's own measurement pins threads per-run via a subprocess re-exec
  (the same `threadpoolctl`-vs-env-var lesson ADR-211/213 both name — the
  env var alone does not reliably reach an already-imported OpenBLAS).

## Gap Before

PLAN slice 5f's own registered question (ADR-213): ADR-213's own N=8 stress
case duplicated the N=4 near-flat fixture's shape onto a SECOND,
INDEPENDENT covariate draw — chosen deliberately to rule out rank-deficiency
after a covariate-REUSE attempt failed that way — and found single-start
already sufficient there, at every thread count tested. But the target
formula's own 13-21 blocks mostly SHARE covariates (`AttdAge`, `PolYear`,
factor levels across `sz(FaceSize, AttdAge)`, `sz(Smoke, AttdAge)`,
`sz(FaceSize, PolYear)`, `sz(Smoke, PolYear)`), which two decoupled copies
say nothing about. **Never measured before this session**: does a
covariate-SHARING N>4 structure behave differently?

**Tier and digest:** N/A for this slice's own measurement — see "No mgcv
comparison" below. ADR-213's own numbers quoted above are pure-Python
internal measurements (no R involved), cited for context only.

## Hypotheses tried

1. **Two independent binary indicators, each scaled onto BOTH an `AttdAge`
   term and a `PolYear` term (mirroring `sz(FaceSize, AttdAge)` /
   `sz(FaceSize, PolYear)` literally) — tried first, REJECTED.** Measured
   directly (`numpy.linalg.matrix_rank` on the assembled design): rank
   deficient by exactly 2 out of 124 columns. SVD confirmed the mechanism
   before writing the diagnostic script the other way: the two smallest
   singular values are `~1e-15` against the next at `1.3e-2`, and their
   null-space vectors load exclusively on the age/year block pair sharing
   one indicator each. An unconstrained `by`-scaled `cr` basis always
   contains the constant function in its span (ADR-200's own finding — no
   identifiability constraint is absorbed on a numeric-`by` smooth), so
   `s(AttdAge, by=Ind)` and `s(PolYear, by=Ind)` sharing the SAME
   indicator each contain the direction `Ind` itself in their column
   space — one exact linear dependency per repeated indicator. Recorded
   here, and in the script's own docstring, so a future session does not
   repeat it blind (the same discipline ADR-213's own rejected-hypothesis
   1 modeled).
2. **Four INDEPENDENT binary indicators, never repeating one across an
   `AttdAge` term and a `PolYear` term (adopted).** `GroupA`/`GroupB` on
   `AttdAge` (k=13, matching `ref`/`by`'s own knots), `GroupC`/`GroupD` on
   `PolYear` (k=6, matching `ti`'s own year margin), each drawn from
   `numpy.random.default_rng(20260831)` (pinned per ADR-074). Measured
   full rank (124/124) and well-conditioned (`cond(XᵀX)≈1.3e7`) before
   the diagnostic script was written the way it is — Anchor 8's "argue,
   don't merely try" applied to a construction choice. **Verdict:
   worked** — see Measurement below.

## No mgcv comparison in this slice

Stated explicitly, per `docs/VERIFICATION_STANDARD.md` §3.2, the identical
status ADR-213 declared for its own two measurements: the claim sentence
cannot be filled in with two distinct computations —
`select_lambdas_continuous_multistart` is compared against
`select_lambdas_continuous` (the single-start default), Polaris's own
code, not a second, independent producer. Nothing here is INDEPENDENT,
ECHO or TRANSPORT by ADR-193's mechanical test; there is no
`right_producer` to name, so no `VerificationClaim` is declared anywhere.
`docs/CONFORMANCE_LEDGER.md`'s new row states the same in its own verdict
column.

## What was built

- `scripts/gam_multistart_shared_covariates_diagnostic.py` — the N=8
  covariate-sharing design (the N=4 fixture's own `ref`/`by`/`ti` plus
  `gA`/`gB`/`gC`/`gD`), and the measurement below. Re-execs itself per
  `OPENBLAS_NUM_THREADS` value, the same pattern
  `gam_multistart_robustness_diagnostic.py` (ADR-213) uses. No production
  code changed — `select_lambdas_continuous`/`select_lambdas_continuous_multistart`
  are used exactly as ADR-213 shipped them.

## Measurement

All three thread counts read directly from the diagnostic script's own
JSON output (`--worker N`); single-start eval counts and the `at_bound`/
`log_lambda` detail were captured with a short standalone follow-up
script calling `select_lambdas_continuous` directly (same design, same
bounds), since the diagnostic's own printed table does not carry those
fields.

| threads | single score | single converged | single evals | multi (best-of-9) score | multi total evals | gap |
|---:|---:|:---:|---:|---:|---:|---:|
| 1 | 602.994904 | True | 441 | 602.994904 | 6444 | 0.000000 |
| 2 | 602.994248 | True | 522 | 602.994248 | 4617 | 0.000000 |
| 4 | 602.994548 | True | 504 | 602.994548 | 5166 | 0.000000 |

**Single-start converged at every thread count, and multi-start's best-of-9
result is identical to it — to the printed digit — at every one of the
three.** `starts[0]` (the bounds-centre, i.e. what single-start alone
tries) is the winner every time; best-of-9 finds nothing new here.

**Spread across threads: single-start `0.000656`, multi-start `0.000656` —
identical.** Read against ADR-213's own two readings on the same axis:

| structure | single-start spread | best-of-9 spread |
|---|---:|---:|
| N=4, near-flat (ADR-211/212/213) | 0.001483 | 0.000006 |
| N=8, covariate-DECOUPLED (ADR-213) | 0.001180 | 0.001165 |
| N=8, covariate-SHARING (this session) | **0.000656** | **0.000656** |

This is the smallest spread of any structure measured across either
slice — roughly 2x tighter than the decoupled N=8 case and better than
2x tighter than the N=4 fixture. ADR-213's own registered reading
question ("if this design's spread sits closer to N=4 than to decoupled
N=8, that is evidence covariate-sharing drives the pathology") is
answered in the negative: this structure sits below both prior readings,
not between them.

**One feature persists regardless of structure.** The MI by-term (block
index 1) lands exactly on the search's own upper bound at every thread
count (`log_lambda[1]=11.0`, `at_bound=True`; full point at 4 threads:
`[7.136, 11.000, 3.315, 2.840, 10.276, 6.471, 8.382, 5.055]`,
`edf_total≈26.0`) — the same "shrunk toward a large, weakly-identified
lambda" signature ADR-211/212 found for this exact term in the N=4
fixture. Here, unlike there, it does not destabilise the rest of the
search: the other seven blocks converge to the identical point regardless
of thread count or starting point.

**Cost.** Best-of-9 costs `~9x`-`~15x` a single search's own function
evaluations (6444/4617/5166 vs. 441/522/504) — inside ADR-213's own
stated `8x`-`21x` range, not a new figure.

## Gap After

PLAN slice 5f's own question — does a covariate-SHARING N>4 structure
behave differently from ADR-213's covariate-DECOUPLED one — is ANSWERED:
no, and if anything this specific construction is MORE stable, not less.
Slice 5f is DONE. What remains open, named rather than dropped: (1) this
is one covariate-sharing construction (independent binary indicators
standing in for `sz`'s own factor levels), not `sz`'s own constrained
parameterisation (slice 6) — evidence about the outer search's own
robustness, not a preview of `sz`'s Stage-A or Stage-B behaviour;
(2) the MI by-term's own at-bound, weakly-identified behaviour persists
structurally across every N tested so far — not new, but not resolved,
and worth remembering if a future structure DOES reproduce the N=4
pathology; (3) whether single-start continues to suffice past N=8, toward
the target's 13-21 blocks, remains untested in any shape.

## Provenance (ADR-193)

No comparison against `mgcv` is made anywhere in this session, the
identical status ADR-213 declared for its own measurements. Both
readings above compare `select_lambdas_continuous_multistart`'s own
output against `select_lambdas_continuous`'s own output — the SAME
producer family, never a second independent implementation, an `mgcv`
fit, or any external reference. Per `docs/VERIFICATION_STANDARD.md` §2's
mechanical test, this is not INDEPENDENT, ECHO or TRANSPORT — those three
exhaust the relationships a comparison *against a second producer* can
have, and there is no second producer here at all. No `VerificationClaim`
is declared; `docs/CONFORMANCE_LEDGER.md`'s new row states this in its
own verdict column. The one place tier-1 R was installed this session
(SETUP step 2, unconditional) was not used for any quantity in this
session's own measurement — no R script was run.

## Oracle version

R 4.3.3 / mgcv 1.9.1 / jsonlite 1.8.8 (local apt, tier 1) — installed per
the routine's SETUP step, not used by any quantity in this session's own
measurement. No tier-3 (CI/pinned-image) dispatch was made this session:
nothing measured here has an `mgcv` side to verify against a pinned
digest.

## Quality gate

- `uv run ruff format scripts/gam_multistart_shared_covariates_diagnostic.py`
  — clean (1 file left unchanged).
- `uv run ruff check scripts/gam_multistart_shared_covariates_diagnostic.py --fix`
  — clean (all checks passed).
- `OPENBLAS_NUM_THREADS=1 uv run pytest tests/ -q -m "not slow"` (full
  suite, no production code changed this session): **[filled in below
  once the run completes]**.
- `uv run pytest tests/qa/ -v --tb=short`: **[filled in below]**.
- `uv run python scripts/perf_history.py`: run once on this PR's initial
  open (ADR-177).

## Definition of done (PLAN slice 5f's own acceptance)

- [x] "The same measurement shape ADR-213 used (single vs. best-of-9,
      thread-pinned at >=2 thread counts, cost stated) on a
      covariate-sharing structure." Met: all three of ADR-213's own
      thread counts (1/2/4), cost stated (~9x-15x).
- [x] "Reporting whichever finding actually results (single suffices /
      multi-start meaningfully helps / neither converges reliably) is
      the deliverable; this is not registered with a predicted answer."
      Met: single suffices, and more decisively than either of ADR-213's
      own readings (identical single/multi scores at every thread count,
      not merely a small gap).

## Follow-ups filed

- None registered as new PLAN slices. What remains open (Gap After,
  above) is named but not filed as its own slice — it is a caveat on
  this slice's own scope (one construction, not `sz` itself) and a
  question slice 6/7 will answer as a byproduct of their own work, not a
  gap this session opened that needs independent tracking.
