"""
Import-layering regression guards for ``polaris_re.core``.

`core/pipeline.py` is the composition root and is granted a CLAUDE.md §6
layering exception to import from `assumptions/`. Historically `core/__init__.py`
*eagerly* re-exported the pipeline symbols, so importing any leaf `core.*`
module (which runs `core/__init__.py`) dragged `pipeline` — and therefore
`assumptions`, mid-initialisation — into the import graph. Importing
`assumptions.mortality` before anything primed `analytics` then raised a
circular ``ImportError``.

These tests pin the fix (ADR-155): each runs in a *fresh* interpreter via
``subprocess`` so Python's module cache cannot mask the ordering bug the way it
does within a single already-primed process.
"""

import subprocess
import sys


def _run_snippet(code: str) -> subprocess.CompletedProcess[str]:
    """Execute ``code`` in a clean interpreter and return the completed process."""
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )


def test_assumptions_mortality_imports_without_priming() -> None:
    """`assumptions.mortality` must import first in a fresh process.

    This is the exact order that raised the circular ``ImportError`` before
    ADR-155 removed the eager pipeline re-export from ``core/__init__.py``.
    """
    result = _run_snippet(
        "from polaris_re.assumptions.mortality import MortalityTable; "
        "print(MortalityTable.__name__)"
    )
    assert result.returncode == 0, (
        "importing polaris_re.assumptions.mortality first regressed to a "
        f"circular import:\n{result.stderr}"
    )
    assert result.stdout.strip() == "MortalityTable"


def test_core_package_does_not_eagerly_import_pipeline() -> None:
    """Importing ``polaris_re.core`` must not pull ``core.pipeline`` into sys.modules.

    The eager re-export is what created the cycle; keeping ``pipeline`` out of a
    bare ``import polaris_re.core`` preserves the ``core`` → (no) ``assumptions``
    layering at package-import time.
    """
    result = _run_snippet(
        "import sys; import polaris_re.core; print('polaris_re.core.pipeline' in sys.modules)"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False", (
        "importing polaris_re.core eagerly dragged in core.pipeline "
        "(and thus the assumptions layer)"
    )


def test_pipeline_symbols_reachable_at_canonical_path() -> None:
    """The pipeline symbols remain importable from their canonical module."""
    result = _run_snippet(
        "from polaris_re.core.pipeline import ("
        "DealConfig, LapseConfig, MortalityConfig, PipelineInputs, build_pipeline"
        "); print('ok')"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
