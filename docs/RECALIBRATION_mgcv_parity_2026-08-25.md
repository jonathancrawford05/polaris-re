# Recalibration — the mgcv parity epic, 2026-08-25

> **Requested by the maintainer** after PR #212, on the reading that *"development
> has completely stalled"* and that candidate root causes should be surfaced before
> choosing a path. This note does two things: reports a measurement run during the
> recalibration that changes the picture, and sets out the causes I think are real.
>
> **Status: for maintainer decision.** Nothing here is adopted. §1's numbers are
> **tier 1 only** and are therefore hypotheses, not results, under
> `ROUTINE_MGCV_PARITY.md`'s own tier discipline — they must not be copied into
> `DECISIONS.md`, `PLAN_*`, `CONTINUATION_*` or a docstring until tier 3 confirms them.

---

## 1. The measurement: slice 6's blocker is localised to one line

The recalibration was going to be planning in the dark, because the cheap
localisation named in PR #212's round-2 review had been filed rather than run —
on my own "follow-on, not a blocker" label. It was run first instead. It took
about twenty minutes and it resolves the open question.

**The experiment.** ADR-208 established that `mgcv`'s criterion and ours rank
`mgcv`'s free-`sp` point and Python's free-`sp` point in *opposite* order. That is
consistent with two different worlds: the criteria are genuinely different
functions of `sp`, or they are the same function up to an additive constant
(identical argmin) and the flip came from elsewhere. Evaluating **both criteria at
the same fixed `sp`**, at eight well-separated points on the same design,
discriminates them — and involves no optimiser at all.

**Result (tier 1: R 4.3.3 / mgcv 1.9.1, n=900, p=86, 4 blocks; the seed-20260825
design the committed probes already use):**

| point | log10(sp) | ours | mgcv | ours − mgcv |
|---|---|---:|---:|---:|
| `mgcv_opt` | [6.70, 9.87, 3.29, 3.03] | 612.6177 | 2347.4335 | **−1734.8158** |
| `python_opt` | [6.75, 9.10, 3.10, 3.05] | 611.8924 | 2347.5543 | **−1735.6618** |
| `flat_2` | [2, 2, 2, 2] | 675.0732 | 2409.8936 | −1734.8204 |
| `flat_4` | [4, 4, 4, 4] | 638.4331 | 2373.2552 | −1734.8222 |
| `flat_6` | [6, 6, 6, 6] | 637.9388 | 2372.7611 | −1734.8223 |
| `mixed_lo_hi` | [3, 8, 2, 5] | 635.0876 | 2373.8142 | **−1738.7266** |
| `mixed_hi_lo` | [8, 3, 5, 2] | 643.1775 | 2379.5948 | **−1736.4173** |
| `mid` | [5, 5, 3, 3] | 623.2026 | 2358.0225 | −1734.8200 |

The large constant (≈ −1734.82) is just a normalisation convention and is harmless.
**The difference is not constant** — spread **3.9108** — so the discrepancy is in
the criterion, at fixed `sp`, with the optimiser and the search entirely out of the
picture. That settles the question ADR-208's amendment left open.

**The pattern is discrete, not smooth.** Five points agree to ~7e-3; three depart by
0.85, 1.60 and 3.91. That is the signature of a rank decision flipping, not a wrong
formula term — and the departures land exactly where the λ's span many decades.

**The mechanism, and the line.** `log|S|₊` is the generalised determinant over the
*positive* eigenvalues of `S = Σⱼ λⱼ Sⱼ`, so it needs a null-space cut.
`gam_reml.reml_score_general` uses a fixed relative tolerance:

```python
positive = eigenvalues[eigenvalues > max(largest, 1e-300) * 1e-10]
```

The design's true rank is **81** (p=86, structural null space 5), and it reads 81 at
tolerances of `1e-12` and `eps·p` at *every* point. At the shipped `1e-10` it reads
**79 or 80** at precisely the points that depart. When the λ's are close together the
spectrum has a clean ~1e10 gap at the null space and any tolerance works; when they
span six decades the gap collapses to ~1e5–1e6 and the cut becomes arbitrary. A
misclassified eigenvalue shifts `log|S|₊` by its logarithm — a discrete jump, which
is exactly the shape observed.

**Causation, not correlation.** Applying only the null-space correction analytically
(counting the eigenvalues between `1e-12` and `1e-10`, which moves the score by
`−Σ log eᵢ / 2` and changes nothing else):

| | spread of (ours − mgcv) |
|---|---:|
| shipped, `1e-10` | 3.910776 |
| corrected, `1e-12` | **0.003281** |
| | **1192× reduction** |

And ADR-208's ranking flip disappears: corrected `delta_ours = −0.1211` against
`delta_mgcv = −0.1208` — same sign, agreeing to 2.7e-4, where the committed reading
has them at **+0.7252 vs −0.1214**.

**Two things this is not.**

1. **`1e-12` is not the fix.** Swapping one hard-coded tolerance for another is the
   tuning PLAN Anchor 8 forbids, and it would work here only by luck of this
   design's spectrum. It is a *diagnostic* that demonstrates causation. The
   principled repair is the one already named as the next hypothesis — Wood (2011)
   §3.1 — which exists precisely so that `Σⱼ λⱼ Sⱼ` is never formed and
   eigendecomposed when the λ's are badly scaled, using a balanced similarity
   transform instead. The measurement says that hypothesis is right and supplies its
   mechanism.
2. **This is tier 1.** Committable numbers need tier 3, and a session should re-run
   it there before any of this enters a permanent document.

**What it changes.** Slice 6 was blocked on a *confirmed but unlocalised* criterion
discrepancy. It is now localised to one function, with a demonstrated cause and a
named principled repair. The residual 0.0033 may be genuine or numerical and is the
next thing to look at, not a blocker.

---

## 2. Was the epic actually stalled?

**Not on throughput.** Fifteen ADRs since 2026-08-15, eight of them genuine
INDEPENDENT parity closures (194, 195, 196/197, 199, 200, 202, 205, 206). Judged as
output, this is one of the more productive stretches in the project.

That distinction matters, because the remedies are opposite: pushing harder on a
direction problem makes it worse. What follows assumes the problem is direction.

---

## 3. Candidate root causes, ranked

### 3.1 The epic has never measured its own headline metric

`PLAN_mgcv_parity_engine.md` Anchor 2 names the **MI contrast on a pinned grid** as
the *primary* acceptance criterion — *"the number that reaches a reader."*

Occurrences of that metric in `CONFORMANCE_LEDGER.md`: **zero.** It has never been
measured, once, in six weeks. ADR-206 named it as unmeasured; ADR-208 named it again.

Everything measured to date is a component (Stage A per term), a synthetic ten-cell
suite, or a Stage-B result on a three-term subset. **There is no number that goes
up.** Nobody — including the maintainer — can say whether the epic is 60% or 95%
complete, because the quantity that would answer that has no value at all.

This is, I think, the actual source of the feeling of stall. Fifteen locally-correct
results moved nothing anyone tracks.

### 3.2 The routine's definition of success has no convergence pressure

Both of these are in `ROUTINE_MGCV_PARITY.md`, and both are individually right:

- *"An INDEPENDENT comparison that DISAGREES is a SUCCESS."*
- *"A gap characterised with evidence and a named next hypothesis is a success."*

Together they mean **a session can always succeed without closing anything.** There
is no rule anywhere that says a gap must eventually be closed, or that names who
closes it, or when. Slice 5b is the illustration: it succeeded, correctly, by
refuting its own prediction and opening a new gap that then blocked slice 6.

### 3.3 File-don't-fix accretion

`CONTINUATION_mgcv_parity_engine.md` now carries **six** open questions, three added
this week — two of them by me. Review discipline correctly says *don't widen a PR's
scope*; nothing anywhere says when a filed item gets worked.

§1 is the clearest case: a twenty-minute measurement that resolved the epic's
blocker sat filed rather than run, because a reviewer — me — labelled it
"follow-on, not a blocker." The label was defensible per-PR and wrong for the epic.

### 3.4 The maintainer is the only closer, and that queue has no cadence

Currently maintainer-reserved and waiting: the `sp` acceptance criterion, the 95%
band labelling, the duration treatment, ADR-204's schema amendment,
`PATTERN_gated_decomposition.md` adoption, the at-bound engine contract, and the
commercial-viability re-rank. Seven items, no schedule.

The routine runs daily; the only person who can close a reserved question does not.
That queue is now the critical path and nothing measures its depth.

### 3.5 The objective has not been re-examined since 2026-08-10

The target is eight terms, 13–21 smoothing parameters, `bs="sz"` and `select=TRUE` —
a substantial reimplementation of `mgcv`. Whether *full parity on that form* is what
a reinsurance pricing engine needs, versus a defensible well-understood GAM that is
verified where it matters, has not been asked since the epic was created.

This is the maintainer's call and I am not making it. But the commercial-viability
re-rank that would inform it is itself one of the six open questions in §3.3, and it
has never happened.

---

## 4. What I would change

Ordered by leverage, all of them maintainer decisions:

1. **Measure Anchor 2's primary metric now, on the three terms that fit.** Partial
   and honest beats absent. It gives the epic a number that moves, and it is the
   single change most likely to dissolve the sense of stall. It does not need slices
   6 and 7 to be worth doing.
2. **Add a closure obligation to the routine.** Something with teeth and a subject:
   an open gap names who closes it and by when, or a session that opens its Nth gap
   must close one first. §3.2 is currently unbounded by construction.
3. **Give the maintainer queue a cadence** — a standing slot that clears reserved
   decisions. Seven items is already the critical path.
4. **Add "run it if it is under an hour" to the review norm.** A cheap measurement
   filed is a cheap measurement lost; §1 cost twenty minutes and had been deferred
   for a day.
5. **Re-ask the scope question** with the commercial-viability re-rank, before slices
   6 and 7 are built. They are the two most expensive slices in the plan.

## 5. What I would not change

The verification discipline is the best thing this project has and none of the above
touches it. ADR-193's provenance rule, the three-tier oracle, the registered
predictions, the refusal to tune a tolerance to make a gap close, and the habit of
retracting a wrong conclusion in place rather than editing it away — those are why
§1 was findable at all. A criterion discrepancy of 0.85 in a score of ~612, at one
point in a four-dimensional space, is not something a looser project would ever
have seen. **The problem is not rigour. It is that rigour has been pointed at
components and never at the objective.**
