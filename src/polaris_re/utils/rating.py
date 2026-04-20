"""
Block-level substandard-rating composition helpers.

A small, framework-agnostic summary of how much of an inforce block is
rated — used by the CLI (``polaris price``) and the Streamlit dashboard
to report the same numbers from a single source of truth.

A policy is considered "rated" when either its ``mortality_multiplier``
exceeds 1.0 or its ``flat_extra_per_1000`` exceeds 0.0. Both halves
matter: cedants sometimes issue flat-extra-only ratings for specific
impairments (e.g. "FE5" for a $5-per-$1,000 flat extra) without changing
the mortality multiplier.
"""

import numpy as np

from polaris_re.core.inforce import InforceBlock

__all__ = ["rating_composition"]


def rating_composition(inforce: InforceBlock) -> dict[str, float | int]:
    """Summarise substandard-rating composition of an inforce block.

    Args:
        inforce: Inforce block to summarise.

    Returns:
        Dict with the following keys:

        - ``n_policies``: Total policy count.
        - ``n_rated``: Policies with multiplier > 1.0 OR flat_extra > 0.0.
        - ``pct_rated_by_count``: ``n_rated / n_policies`` (0.0-1.0).
        - ``pct_rated_by_face``: Face-weighted share of rated lives
          (0.0-1.0).
        - ``face_weighted_mean_multiplier``: Face-weighted average
          ``mortality_multiplier`` across the WHOLE block (standard
          lives contribute 1.0). The natural "average mortality load"
          number a pricing actuary reads.
        - ``max_multiplier``: Max per-policy multiplier.
        - ``max_flat_extra_per_1000``: Max per-policy flat-extra.
    """
    multipliers = inforce.mortality_multiplier_vec
    flat_extras = inforce.flat_extra_vec
    face = inforce.face_amount_vec

    rated_mask = (multipliers > 1.0) | (flat_extras > 0.0)
    n_policies = int(inforce.n_policies)
    n_rated = int(rated_mask.sum())
    total_face = float(face.sum())
    rated_face = float(face[rated_mask].sum())

    weighted_mean_multiplier = (
        float(np.dot(multipliers, face) / total_face) if total_face > 0.0 else 1.0
    )

    return {
        "n_policies": n_policies,
        "n_rated": n_rated,
        "pct_rated_by_count": (n_rated / n_policies) if n_policies else 0.0,
        "pct_rated_by_face": (rated_face / total_face) if total_face > 0.0 else 0.0,
        "face_weighted_mean_multiplier": weighted_mean_multiplier,
        "max_multiplier": float(multipliers.max()) if n_policies else 1.0,
        "max_flat_extra_per_1000": float(flat_extras.max()) if n_policies else 0.0,
    }
