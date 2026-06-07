"""Portfolio config loader for the Streamlit dashboard portfolio page.

The dashboard upload flow gives the user two file_uploader widgets: one
for the YAML / JSON portfolio config and one (multi-file) for the per-deal
inforce CSVs referenced by the config. The CLI's
``_build_portfolio_from_config`` is the canonical parser and stays the
single source of truth for portfolio config semantics; this module is the
thin adapter that:

- Persists the uploaded files to a working directory so the CLI parser
  sees real paths (its ``inforce_csv:`` resolver reads CSVs by path).
- Rewrites the YAML's ``inforce_csv:`` entries by basename so a YAML
  referencing ``data/inputs/portfolio_sample/deal_a_...csv`` resolves to
  the uploaded ``deal_a_...csv`` blob.
- Converts the CLI parser's ``typer.Exit`` (used for user-facing errors)
  into ``PolarisValidationError`` so the Streamlit page can render the
  message without a SystemExit hijacking the session.

The loader does NOT duplicate the per-deal parser (mortality / lapse /
deal / policies); that schema lives in ``polaris_re.cli`` and is shared
unchanged.
"""

import tempfile
from pathlib import Path
from typing import cast

import typer

from polaris_re.analytics.portfolio import Portfolio
from polaris_re.core.exceptions import PolarisValidationError

__all__ = [
    "load_portfolio_from_config_path",
    "load_portfolio_from_uploaded",
]


def load_portfolio_from_config_path(config_path: Path) -> tuple[Portfolio, float]:
    """Build a ``Portfolio`` from a YAML / JSON config on disk.

    Thin wrapper around the CLI's ``_build_portfolio_from_config`` that
    converts ``typer.Exit`` (the CLI's user-error signal) into a regular
    ``PolarisValidationError`` so Streamlit callers see a Python exception
    instead of a SystemExit.

    Returns:
        ``(portfolio, hurdle_rate)`` — same shape as the CLI helper.
    """
    from polaris_re.cli import _build_portfolio_from_config

    if not config_path.exists():
        raise PolarisValidationError(f"Portfolio config not found: {config_path}")
    try:
        # CLI helper's return type is tuple[object, float] for historical
        # reasons (lazy import of Portfolio in the CLI module); cast to the
        # precise type for downstream callers.
        return cast(tuple[Portfolio, float], _build_portfolio_from_config(config_path))
    except typer.Exit as exc:
        raise PolarisValidationError(
            f"Failed to build portfolio from {config_path.name}: the CLI "
            f"parser rejected the config. See stderr for the specific error."
        ) from exc


def load_portfolio_from_uploaded(
    yaml_text: str,
    csv_files: dict[str, bytes],
    workdir: Path | None = None,
) -> tuple[Portfolio, float]:
    """Build a ``Portfolio`` from an in-memory YAML string + uploaded CSV bytes.

    Persists ``csv_files`` (filename → bytes) and a path-rewritten YAML to
    ``workdir`` (a fresh temp directory by default), then delegates to
    :func:`load_portfolio_from_config_path`.

    The YAML's ``inforce_csv:`` references are matched against ``csv_files``
    by basename; a deal pointing at a CSV that was not uploaded raises
    ``PolarisValidationError`` with the missing basename listed.

    Args:
        yaml_text:  Raw YAML (or JSON-superset) string from a file_uploader.
        csv_files:  Mapping of CSV filename (basename or path) → bytes.
        workdir:    Optional directory to persist files into. Defaults to a
                    fresh ``tempfile.mkdtemp`` directory (not cleaned up;
                    callers that care should pass a managed path).

    Returns:
        ``(portfolio, hurdle_rate)``.
    """
    import yaml as yaml_mod  # type: ignore[import-untyped]

    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="polaris_portfolio_"))
    workdir.mkdir(parents=True, exist_ok=True)

    # Persist CSV blobs by basename so the YAML's inforce_csv resolves cleanly.
    persisted: dict[str, Path] = {}
    for fname, blob in csv_files.items():
        target = workdir / Path(fname).name
        target.write_bytes(blob)
        persisted[target.name] = target

    try:
        data = yaml_mod.safe_load(yaml_text)
    except yaml_mod.YAMLError as exc:
        raise PolarisValidationError(f"Malformed portfolio YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise PolarisValidationError(
            f"Portfolio config must be a mapping, got {type(data).__name__}."
        )

    deals = data.get("deals")
    if not isinstance(deals, list) or len(deals) == 0:
        raise PolarisValidationError("Portfolio config must contain a non-empty 'deals' list.")

    for deal in deals:
        if not isinstance(deal, dict):
            continue
        inforce_csv = deal.get("inforce_csv")
        if inforce_csv is None:
            continue
        basename = Path(str(inforce_csv)).name
        resolved = persisted.get(basename)
        if resolved is None:
            raise PolarisValidationError(
                f"Deal {deal.get('deal_id')!r} references inforce_csv "
                f"{inforce_csv!r} but no uploaded CSV matches basename "
                f"{basename!r}. Uploaded: {sorted(persisted.keys())}."
            )
        deal["inforce_csv"] = str(resolved)

    config_path = workdir / "portfolio.yaml"
    config_path.write_text(yaml_mod.safe_dump(data))

    return load_portfolio_from_config_path(config_path)
