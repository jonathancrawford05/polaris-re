# Gated decomposition — a constraint that builds verified parts, and how to end it

> **Status: PROPOSED.** Not adopted. This is a retrospective on Anchor 7 written at
> maintainer request (2026-08-24) after the anchor was amended by ADR-207; it proposes
> requirements for future gates and needs maintainer adoption before it binds anything.
>
> **Scope: portable.** Written from this project's `mgcv` parity epic, but the pattern is
> about re-implementation work in general — any effort that must match an external
> reference (a vendor system, a published algorithm, a legacy engine) component by
> component. Companion to `VERIFICATION_STANDARD.md`, which governs what counts as
> evidence; this governs when you are permitted to assemble.

---

## 1. The observation

Anchor 7 said *"the existing engine stays."* It was written to protect a shipped engine,
for three stated reasons: committed reports came from it, the QA goldens depend on it, and
the λ=0 oracle chain needs it alive. None of those reasons mentions decomposition.

But its **effect** was to forbid assembling a replacement. And that effect, not its stated
purpose, is what shaped eleven slices of work: the developer could build and verify
*components*, and could not build the thing that composes them. The result was nine
independently tier-3-verified modules — bases, family, fitter, REML criterion, the λ
search, covariance, derivatives — each measured against `mgcv` in isolation, before
anything was assembled.

That is an unusual and valuable position to be in, and it was not the anchor's stated
goal. It was a side effect nobody wrote down.

## 2. What the constraint bought

**Fault localisation.** Nine components with independent tier-3 results means a later
assembly disagreement cannot be blamed on "somewhere in the stack." `WORK_ORDER_multi_term_assembly.md`
§4 can register a prediction — *a disagreement at free `sp` localises to λ selection, not
to the bases, fitter or criterion* — precisely because every other step already has its
own number. A big-bang integration cannot make that claim; a single end-to-end diff hides
which of nine things is wrong.

**Understanding, not just coverage.** Each component had to be understood well enough to
state what it should equal and why. ADR-205's `ti()` work is the example: a hand-replica
was out by 182 in `X` until instrumenting `mgcv` revealed that `cr` sets `noterp`. That
finding exists because someone was forced to make one term agree in isolation. Assembled
first, it would have been one contribution to an aggregate residual.

**Order of operations.** The verified components are reusable in a way an assembled engine
is not. They are what the eventual production path is built *from* — the work was not
thrown away when the gate opened.

## 3. What it cost

**Homeless components.** Nine verified modules and no production path any of them was
permitted to belong to. Each had to justify itself as a conformance artifact.

**Three namings, zero buildings.** ADRs 199, 200 and 205 each stopped at Stage A or N=2
and each named the same missing assembler as its blocker. Named three times, built zero
times, because nobody schedules scaffolding.

**A framing distortion at the boundary — the sharpest cost.** When the assembler was
finally built (ADR-206), it was built as `assemble_multiterm_design(r_case: RMultiTermRecipe)`
— a function taking the *reference implementation's own JSON payload* as its input, at
fixed `sp`. That is a harness shape, not an engine shape. It was the correct shape under
the constraint, because "harness" was the only category the work was permitted to occupy.

Note what that means against this project's other standard: an unconditioned gate pushes
work into the category it permits, and when that category is "test harness," the work
adopts test-harness shapes — including taking the reference's output as an input, which is
the exact hazard `VERIFICATION_STANDARD.md` §2 exists to catch. The gate did not cause a
mislabelled comparison here (ADR-206's `eta` claim is genuinely INDEPENDENT, and the
signature test confirms it). But it applied pressure in that direction, which is worth
knowing about in advance.

## 4. The diagnosis

**The defect was not the constraint. It was that the constraint had no release condition.**

Anchor 7 stated what was forbidden and never stated what would end it. So it could not be
opened by anyone doing the work — only by a maintainer noticing, from outside, that it had
outlived its usefulness. That is what happened, eleven slices in.

Two consequences follow, and both are general:

1. **A gate justified on grounds A but valuable for reason B is fragile.** Anchor 7's
   three stated reasons were all about protecting the shipped engine. ADR-204's provenance
   stamps discharged one of them. Had the other two been discharged, the anchor would have
   fallen on its stated grounds — and the decomposition benefit, never written down, would
   have vanished silently with it. The project would have lost something it did not know
   it had.

2. **A gate with no release condition is indistinguishable from a permanent prohibition**
   to everyone downstream of it, and gets planned around rather than satisfied. Three ADRs
   naming the same missing piece is what "planned around" looks like.

## 5. The refined pattern

A construction gate — any rule of the form *"you may not build X yet"* — should carry four
things. Anchor 7 carried one.

| | requirement | Anchor 7 | why |
|---|---|---|---|
| 1 | **Purpose**, including emergent benefits once noticed | stated (engine protection); the decomposition benefit never recorded | a benefit nobody wrote down cannot survive the repeal of the stated reason |
| 2 | **Release condition**, stated up front and checkable | absent | without it, only an outsider can open the gate |
| 3 | **Re-examination trigger** — re-derive the gate whenever one stated reason is discharged | absent | ADR-204 discharged a reason; nothing prompted a re-read |
| 4 | **A named destination** for work built under it | absent | otherwise components are scaffolding, and nobody schedules scaffolding |

**On (2), the release condition.** Make it a property of the work, not a date or a
judgement call. For decomposition gates the natural form is *coverage of the critical
path*: "assembly is permitted once every component on the critical path carries an
INDEPENDENT result at the required tier." Here that condition was **already satisfied**
by the time ADR-199 landed — every component the three-term assembly needs was verified —
so a gate carrying it would have opened itself, on schedule, without maintainer
intervention.

**On (4), the destination.** State where components live when the gate opens, at the time
the gate is written. "These become `PolarisGAM`" costs one sentence and removes the entire
homelessness problem — the work is a staged build of a named thing rather than an
open-ended pile of test fixtures.

## 6. Applying it

When writing a gate, fill in all four lines. If line 2 cannot be written, that is the
finding: a constraint whose end you cannot describe is a decision you have not finished
making.

```
GATE:        <what may not be built yet>
PURPOSE:     <why — and revise this when you notice a benefit you did not intend>
RELEASE:     <the checkable condition that ends it>
RE-EXAMINE:  <whenever one of PURPOSE's reasons is discharged>
DESTINATION: <where work built under this gate goes when it opens>
```

Worked example, Anchor 7 as it should have read:

```
GATE:        No replacement engine; no caller re-pointed.
PURPOSE:     (a) committed reports were produced by the old engine; (b) QA goldens
             depend on it; (c) the λ=0 oracle chain needs it alive; (d) — added once
             noticed — forcing component-wise verification before assembly, so that a
             later disagreement localises.
RELEASE:     Every component on the critical path carries an INDEPENDENT tier-3 result.
             (a)-(c) continue to hold the *old engine* alive independently of this.
RE-EXAMINE:  On discharge of any of (a)-(c). ADR-204 discharged (a) on 2026-08-24.
DESTINATION: PolarisGAM, built from the verified components.
```

## 7. What this does not claim

- **The counterfactual is unmeasured.** A gate with a release condition would have opened
  around ADR-199 rather than ADR-207. Whether the intervening slices would have gone
  better is speculation — they produced real verified results, and ADR-205's `noterp`
  finding might not have surfaced at all under a looser regime. The claim here is narrow:
  the gate should have been able to open itself. It is *not* that the work done under it
  was wasted, or that less constraint would have been better.
- **This is not an argument for fewer constraints.** The observation runs the other way:
  the constraint was productive, and its benefit went unrecorded for eleven slices because
  it was accidental. The proposal is to state gates more fully, not to use fewer of them.
- **Not all gates are decomposition gates.** A safety gate (*"never label an interval a
  95% band without maintainer sign-off"*) is meant to be permanent and has no release
  condition by design. Requirement 2 should read "release condition, or an explicit
  statement that there is none and why."

## 8. Provenance

Retrospective requested by the maintainer, 2026-08-24, immediately after ADR-207:

> *"As I read the situation, the anchor 7 effectively forced the developer to build
> individual components and understand their place in the parity attainment, until they
> were permitted to construct a more complete representation of the underlying mechanism
> that parity seems to mimic. Maybe we could refine the pattern for future use (this
> project or others)."*

That reading supplies the half ADR-207 missed. ADR-207 records the anchor's cost — it was
written to justify amending it — and treats the constraint as an obstacle that had
outlived its reasons. It does not credit the constraint with producing the nine verified
components in the first place. Both readings are correct, and §4 is the synthesis: a
productive constraint that could not end itself.
