"""Append-only versioned persistence for experience-derived assumption scales.

The A4' experience pipeline (``polaris experience improvement``) emits a
data-driven :class:`~polaris_re.assumptions.improvement.MortalityImprovement`
(``ImprovementScale.CUSTOM``) — an experience-fitted mortality-improvement
surface or projection. That bare artifact carries the ``MI_x(y)`` grid but *no*
provenance: which experience study produced it, as of what study date, and at
what credibility. Freezing an assumption basis for a priced deal needs that
provenance preserved and immutable.

This module wraps a CUSTOM scale in an :class:`AssumptionVersion` record
(study-date + credibility + label tags) and persists it through an
**append-only** :class:`AssumptionVersionStore` under
``data/assumption_versions/{kind}/{version_id}.json``. Re-saving the same study
date allocates a fresh sequence number rather than overwriting — the history of
every basis an actuary has frozen is preserved for audit. Nothing here touches
the pricing path or any golden; the store is a side artifact consumed later by
the ``--config`` wiring (Slice 4b-3).

Records are keyed by study date and an allocated sequence, never by the wall
clock (ADR-074 guard) — the store is fully deterministic given its inputs.
"""

import json
import os
from datetime import date
from pathlib import Path

from pydantic import Field, field_validator, model_validator

from polaris_re.assumptions.improvement import ImprovementScale, MortalityImprovement
from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError

__all__ = [
    "DEFAULT_ASSUMPTION_KIND",
    "AssumptionVersion",
    "AssumptionVersionStore",
    "default_store_root",
]

# The only assumption kind versioned in this slice — an experience-derived
# mortality-improvement (CUSTOM) scale. Kept as a module constant so later
# slices (lapse, base mortality) can add sibling kinds without changing the
# store contract.
DEFAULT_ASSUMPTION_KIND = "mortality_improvement"


def default_store_root() -> Path:
    """Default assumption-version store root: ``$POLARIS_DATA_DIR/assumption_versions``.

    ``data/assumption_versions`` when the env var is unset, mirroring the
    mortality-table directory resolution. This is the single default shared by
    the ``polaris experience save/list`` CLI (via ``_resolve_store_dir``) and the
    ``--config`` improvement selector (A4' Slice 4b-3), so both resolve the store
    root identically.
    """
    return Path(os.environ.get("POLARIS_DATA_DIR", "data")) / "assumption_versions"


class AssumptionVersion(PolarisBaseModel):
    """One immutable, provenance-tagged version of a data-driven assumption.

    Wraps an experience-derived ``ImprovementScale.CUSTOM``
    :class:`MortalityImprovement` with the study metadata that makes it
    auditable: the ``study_date`` the experience data was observed as of, an
    optional ``credibility`` weight, and free-form ``label`` / ``notes`` tags.
    The ``version_id`` is allocated by the store (``{study_date}-{seq:03d}``)
    and is unique within a ``kind``.
    """

    version_id: str = Field(
        description="Store-allocated identifier, unique within kind "
        "(format: '{study_date}-{seq:03d}', e.g. '2024-12-31-001').",
    )
    kind: str = Field(
        default=DEFAULT_ASSUMPTION_KIND,
        description="Assumption family this version belongs to.",
    )
    study_date: date = Field(
        description="Calendar date the experience data was observed as of "
        "(pinned, never the wall clock).",
    )
    credibility: float | None = Field(
        default=None,
        description="Optional credibility weight assigned to this basis, in [0, 1].",
    )
    label: str | None = Field(
        default=None,
        description="Optional short human label (e.g. a segment or treaty tag).",
    )
    notes: str | None = Field(
        default=None,
        description="Optional free-form provenance note (e.g. the source study).",
    )
    improvement: MortalityImprovement = Field(
        description="The versioned experience-derived CUSTOM improvement scale.",
    )

    @field_validator("credibility")
    @classmethod
    def _validate_credibility(cls, value: float | None) -> float | None:
        """Credibility, when supplied, is a weight in the unit interval."""
        if value is not None and not (0.0 <= value <= 1.0):
            raise PolarisValidationError(f"credibility must be in [0, 1], got {value}.")
        return value

    @model_validator(mode="after")
    def _require_custom_scale(self) -> "AssumptionVersion":
        """Only data-driven CUSTOM scales carry the study/credibility provenance."""
        if self.improvement.scale is not ImprovementScale.CUSTOM:
            raise PolarisValidationError(
                "AssumptionVersion persists experience-derived CUSTOM scales only; "
                f"got scale {self.improvement.scale.value!r}. Emit one with "
                "`polaris experience improvement`."
            )
        return self


class AssumptionVersionStore:
    """Append-only filesystem store for :class:`AssumptionVersion` records.

    Layout: ``{root}/{kind}/{version_id}.json``. :meth:`save` allocates the next
    sequence for a ``(kind, study_date)`` pair, so re-saving the same study date
    never overwrites an earlier version — the full history is preserved for
    audit. The store is deterministic: the same sequence of saves against a
    fresh root always yields the same ``version_id``s.
    """

    def __init__(self, root: Path) -> None:
        """Bind the store to a root directory (created lazily on first save)."""
        self.root = Path(root)

    def _kind_dir(self, kind: str) -> Path:
        return self.root / kind

    def _next_sequence(self, kind: str, study_date: date) -> int:
        """The next 1-based sequence for this study date (1 + the current max)."""
        kind_dir = self._kind_dir(kind)
        if not kind_dir.is_dir():
            return 1
        prefix = f"{study_date.isoformat()}-"
        used = [
            int(path.stem[len(prefix) :])
            for path in kind_dir.glob(f"{prefix}*.json")
            if path.stem[len(prefix) :].isdigit()
        ]
        return 1 + max(used, default=0)

    def save(
        self,
        improvement: MortalityImprovement,
        study_date: date,
        *,
        credibility: float | None = None,
        label: str | None = None,
        notes: str | None = None,
        kind: str = DEFAULT_ASSUMPTION_KIND,
    ) -> AssumptionVersion:
        """Persist an improvement scale as a new immutable version.

        A fresh ``version_id`` (``{study_date}-{seq:03d}``) is allocated so an
        existing record is never overwritten. Raises
        :class:`PolarisValidationError` if the allocated path already exists (a
        defensive append-only guard — it should not happen given sequence
        allocation).
        """
        seq = self._next_sequence(kind, study_date)
        version_id = f"{study_date.isoformat()}-{seq:03d}"
        version = AssumptionVersion(
            version_id=version_id,
            kind=kind,
            study_date=study_date,
            credibility=credibility,
            label=label,
            notes=notes,
            improvement=improvement,
        )
        kind_dir = self._kind_dir(kind)
        kind_dir.mkdir(parents=True, exist_ok=True)
        path = kind_dir / f"{version_id}.json"
        if path.exists():
            raise PolarisValidationError(
                f"assumption version {version_id!r} already exists at {path} "
                "(append-only store never overwrites)."
            )
        path.write_text(version.model_dump_json(indent=2), encoding="utf-8")
        return version

    def load(self, version_id: str, *, kind: str = DEFAULT_ASSUMPTION_KIND) -> AssumptionVersion:
        """Load a single version by id. Raises if it is not present."""
        path = self._kind_dir(kind) / f"{version_id}.json"
        if not path.is_file():
            raise PolarisValidationError(
                f"assumption version {version_id!r} not found under {self._kind_dir(kind)}."
            )
        return AssumptionVersion.model_validate_json(path.read_text(encoding="utf-8"))

    def list_versions(self, kind: str | None = None) -> list[AssumptionVersion]:
        """List stored versions, sorted by (kind, study_date, version_id).

        With ``kind=None`` every kind under the root is scanned; otherwise only
        the named kind. Returns an empty list if the store (or kind) is absent.
        """
        if not self.root.is_dir():
            return []
        kind_dirs = (
            [self._kind_dir(kind)]
            if kind is not None
            else sorted(p for p in self.root.iterdir() if p.is_dir())
        )
        versions: list[AssumptionVersion] = []
        for kind_dir in kind_dirs:
            if not kind_dir.is_dir():
                continue
            for path in kind_dir.glob("*.json"):
                try:
                    versions.append(
                        AssumptionVersion.model_validate_json(path.read_text(encoding="utf-8"))
                    )
                except (json.JSONDecodeError, ValueError) as exc:
                    raise PolarisValidationError(
                        f"corrupt assumption version file {path}: {exc}"
                    ) from exc
        versions.sort(key=lambda v: (v.kind, v.study_date, v.version_id))
        return versions
