"""Term specifications for the ``mgcv``-parity GAM engine.

Slice 1 of ``docs/PLAN_mgcv_parity_engine.md``, Anchor 3: **a term specification is
data, not code.** The engine the epic builds takes a list of term objects (basis, ``k``,
knots, ``by`` variable, factor, penalty order) plus a family / link / weights / offset
spec, so moving between model configurations — which is the maintainer's actual
workflow, per PLAN §1 — is editing data rather than writing a new module. New
conformance cases are then fixtures, not new modules.

Nothing here builds a design matrix. :class:`TermSpec` and :class:`ModelSpec` describe
what to build; the R-side extractor and the (not yet written) Python basis layer read
them. Keeping the description inert is what lets the same object serialise into the
R-side exchange, appear in a test fixture, and describe a term nobody has implemented
yet without any of the three needing to agree on how construction works.

``@dataclass(frozen=True)``, not a Pydantic model, deliberately matching
:mod:`polaris_re.analytics.experience_mgcv_conformance`'s ``DesignSpec`` /
``ConformanceCell`` / ``MetricSpec`` next door — this module extends that one's exchange
machinery to per-term granularity, and a caller reading both should see one convention,
not two. CLAUDE.md's Pydantic-first rule is aimed at the domain's business objects
(policy, treaty, assumptions); term specs are the conformance harness's own internal
data, the same class of object those three already are.

PLAN Anchor 4 — knots and ``k`` are inputs, never tuned: :attr:`TermSpec.knots` is
``None`` only to mean "use mgcv's default placement", and the engine must never derive
its own knots when they are supplied.
"""

from dataclasses import dataclass, field

from polaris_re.core.exceptions import PolarisValidationError

__all__ = [
    "SUPPORTED_BASES",
    "ModelSpec",
    "TermSpec",
]

SUPPORTED_BASES: tuple[str, ...] = ("cr", "ti", "sz", "raw")
"""The basis kinds PLAN §3 puts in scope, plus ``"raw"``.

``"cr"`` — Wood's cubic regression spline (slice 2). ``"ti"`` — tensor interaction with
marginal main effects excluded (slice 5). ``"sz"`` — sum-to-zero factor-smooth
interaction (slice 6). ``"raw"`` is not one of ``mgcv``'s basis classes: it names a term
whose design and penalty are supplied directly, the existing tensor MI surface's own
route through ``paraPen`` (ADR-189 decision 1). A ``"raw"`` term carries no ``k`` and no
knots — the caller supplies the matrices, not a recipe for building them — which is why
slice 1's harness can be proven against the already-verified tensor design without
either side needing an ``mgcv`` smooth-class equivalent for it."""


@dataclass(frozen=True)
class TermSpec:
    """One smooth or parametric term, described rather than built.

    Args:
        label: The term's name, matching ``mgcv``'s own labelling convention
            (e.g. ``"s(AttdAge)"``, ``"ti(AttdAge,PolYear)"``) so a Stage-A comparison
            can key its two sides by the same string.
        variables: The term's covariate(s), in the order ``mgcv`` would take them —
            one for ``s()``, two or more for ``ti()`` / ``te()``.
        basis: One of :data:`SUPPORTED_BASES`.
        k: Basis dimension per variable, in the same order as :attr:`variables`. A
            single-margin term still carries a length-1 tuple, so every term's ``k``
            has the same shape as its ``variables`` regardless of dimension.
        knots: Supplied knot locations per variable, as ``((variable, locations), ...)``
            pairs, or ``None`` to mean "let ``mgcv`` place them" (Anchor 4). A tuple of
            pairs rather than a ``dict``, so a frozen :class:`TermSpec` is actually
            immutable and hashable — a ``dict`` field defeats both (PR #196 review
            [P2]). When present, every named variable must be one the term actually
            has, and a variable may be omitted to mean "default for this margin only"
            — matching ``mgcv``'s own ``knots=list(...)`` partial-supply behaviour. Use
            :meth:`knots_by_variable` for dict-style lookup.
        by: A numeric ``by`` variable scaling the basis (e.g. the MI term's
            ``StudyYear_C``), or ``None``. Mutually exclusive with :attr:`factor`
            being ``True`` — ``mgcv`` has both a numeric-``by`` smooth and a
            factor-smooth (``bs="sz"``/``"fs"``), and they are different constructions.
        factor: Does this term vary by an unpenalized factor level (the ``sz``/``fs``
            family), as opposed to being scaled by a numeric ``by``?
        penalty_order: Derivative order per penalty, where the basis has more than one
            (``cr`` has one; ``ti`` and ``sz`` can carry one per margin). ``None`` means
            "``mgcv``'s default for this basis" rather than "no penalty" — every
            basis in :data:`SUPPORTED_BASES` other than an unpenalized parametric
            term is penalized.
        n_levels: Number of factor levels for a ``basis="sz"`` term (``mgcv``'s
            ``length(levels(fac))``) — an input, not derived from data, the same
            Anchor-4 discipline ``k``/``knots`` already follow: a factor level
            absent from one particular sample must not silently shrink the term.
            Must be ``None`` for any other basis. Optional even for ``"sz"``:
            :func:`~polaris_re.analytics.gam_stage_a.build_python_sz_term`'s
            narrower Stage-A harness takes ``n_levels`` as its own explicit
            argument (the R-side recipe's ``"n_levels"`` field) rather than
            reading it here; :func:`~polaris_re.analytics.gam_model.assemble_model_design`
            (the ``ModelSpec``-driven multi-term path, slice 6b) is what requires
            it set on the spec, and raises if it is not.
    """

    label: str
    variables: tuple[str, ...]
    basis: str
    k: tuple[int, ...] = field(default_factory=tuple)
    knots: tuple[tuple[str, tuple[float, ...]], ...] | None = None
    by: str | None = None
    factor: bool = False
    penalty_order: tuple[int, ...] | None = None
    n_levels: int | None = None

    def knots_by_variable(self) -> dict[str, tuple[float, ...]]:
        """:attr:`knots` as a plain ``dict``, computed on demand.

        Never stored: a stored ``dict`` is exactly what made a "frozen" spec mutable
        and unhashable (PR #196 review [P2]) — this recomputes a fresh one every call
        instead.
        """
        return {} if self.knots is None else dict(self.knots)

    def __post_init__(self) -> None:
        if not self.label:
            raise PolarisValidationError("A TermSpec needs a non-empty label.")
        if not self.variables:
            raise PolarisValidationError(f"TermSpec {self.label!r} names no variables.")
        if self.basis not in SUPPORTED_BASES:
            raise PolarisValidationError(
                f"TermSpec {self.label!r} has basis {self.basis!r}; supported bases "
                f"are {SUPPORTED_BASES}."
            )
        if self.basis == "raw":
            if self.k:
                raise PolarisValidationError(
                    f"TermSpec {self.label!r} is basis='raw' (design and penalty "
                    f"supplied directly) and must not carry k — there is no recipe "
                    f"for mgcv to reproduce."
                )
            if self.knots is not None:
                raise PolarisValidationError(
                    f"TermSpec {self.label!r} is basis='raw' (design and penalty "
                    f"supplied directly) and must not carry knots — there is no "
                    f"recipe for mgcv to place them against."
                )
        elif self.basis == "ti" and len(self.variables) < 2:
            raise PolarisValidationError(
                f"TermSpec {self.label!r} is basis='ti' with variables "
                f"{self.variables}; a tensor interaction needs at least two margins."
            )
        elif self.basis == "sz":
            # mgcv's own asymmetry: `s(FaceSize, AttdAge, bs="sz", k=13, xt=list(bs="cr"))`
            # (PLAN §1) names a factor variable (FaceSize) and a smoothed margin
            # (AttdAge), but k is a SINGLE scalar — the smoothed margin's basis
            # dimension. The factor variable contributes levels, not a k of its own.
            if len(self.variables) != 2:
                raise PolarisValidationError(
                    f"TermSpec {self.label!r} is basis='sz' with variables "
                    f"{self.variables}; sz names exactly two (a factor and the "
                    f"smoothed margin)."
                )
            if len(self.k) != 1:
                raise PolarisValidationError(
                    f"TermSpec {self.label!r} is basis='sz' with k={self.k!r}; sz "
                    f"takes exactly one k — the smoothed margin's basis dimension, "
                    f"not one per variable."
                )
            if self.n_levels is not None and self.n_levels < 2:
                raise PolarisValidationError(
                    f"TermSpec {self.label!r} is basis='sz' with n_levels="
                    f"{self.n_levels!r}; sz needs at least 2 factor levels."
                )
        elif len(self.k) != len(self.variables):
            raise PolarisValidationError(
                f"TermSpec {self.label!r} has {len(self.variables)} variable(s) but "
                f"k={self.k!r} names {len(self.k)}; one k per variable is required."
            )
        if self.knots is not None:
            knot_vars = [pair[0] for pair in self.knots]
            duplicate_vars = sorted({v for v in knot_vars if knot_vars.count(v) > 1})
            if duplicate_vars:
                raise PolarisValidationError(
                    f"TermSpec {self.label!r} supplies knots more than once for "
                    f"{duplicate_vars} — each variable may appear at most once."
                )
            unknown = sorted(set(knot_vars) - set(self.variables))
            if unknown:
                raise PolarisValidationError(
                    f"TermSpec {self.label!r} supplies knots for {unknown}, which "
                    f"{'is' if len(unknown) == 1 else 'are'} not in its variables "
                    f"{self.variables}."
                )
        if self.by is not None and self.factor:
            raise PolarisValidationError(
                f"TermSpec {self.label!r} sets both by={self.by!r} and factor=True — "
                f"a numeric-by smooth and a factor-smooth are different mgcv "
                f"constructions; a term is one or the other."
            )
        if self.basis != "sz" and self.n_levels is not None:
            raise PolarisValidationError(
                f"TermSpec {self.label!r} has basis={self.basis!r} but sets "
                f"n_levels={self.n_levels!r} — only a basis='sz' term has a "
                f"factor-level count."
            )


@dataclass(frozen=True)
class ModelSpec:
    """A family / link / weights / offset spec plus the terms it fits over.

    PLAN Anchor 5: weights and offset are orthogonal controls, both supported, and
    neither is inferred from the other — an ``offset`` makes a model relative and
    ``weights`` says how much each row counts in the likelihood, and supplying both is
    a caller decision this object records rather than resolves.

    Args:
        family: ``mgcv`` family name, e.g. ``"binomial"``, ``"poisson"``,
            ``"quasipoisson"``.
        link: Link function name, e.g. ``"cloglog"``, ``"logit"``, ``"log"``.
        terms: Every term in the model, parametric and smooth alike.
        weights_column: Name of the prior-weights column (e.g. exposure), or ``None``.
        offset_column: Name of the offset column, or ``None``. See Anchor 5's table:
            the target formula uses weights with no offset; the existing polaris engine
            uses an offset. Both idioms are represented, never combined into one field.
    """

    family: str
    link: str
    terms: tuple[TermSpec, ...]
    weights_column: str | None = None
    offset_column: str | None = None

    def __post_init__(self) -> None:
        if not self.family:
            raise PolarisValidationError("A ModelSpec needs a non-empty family.")
        if not self.link:
            raise PolarisValidationError("A ModelSpec needs a non-empty link.")
        if not self.terms:
            raise PolarisValidationError("A ModelSpec needs at least one term.")
        labels = [t.label for t in self.terms]
        duplicates = sorted({label for label in labels if labels.count(label) > 1})
        if duplicates:
            raise PolarisValidationError(
                f"ModelSpec has duplicate term labels {duplicates} — each term must "
                f"be addressable by a unique label for Stage A to key its comparison."
            )
