"""
Import-layering regression guards for ``polaris_re.core``.

The deal composition root (``DealConfig``/``build_pipeline``/etc.) imports from
``assumptions/`` — which the CLAUDE.md §6 rule forbids ``core/`` from doing.
ADR-156 relocated that module out of ``core/`` to the package top level
(``polaris_re.pipeline``), so ``core`` no longer imports ``assumptions`` at all
and the §6 rule holds without exception. ADR-155 was the earlier symptom-only
fix (removing an eager pipeline re-export from ``core/__init__.py``, which had
made a leaf ``core.*`` import drag ``pipeline`` — and thus ``assumptions``,
mid-initialisation — into the graph, raising a latent circular ``ImportError``).

These tests pin both invariants: each runs in a *fresh* interpreter via
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
    ADR-155 removed the eager pipeline re-export from ``core/__init__.py`` and
    ADR-156 moved the composition root out of ``core/`` entirely.
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


def test_core_package_does_not_import_pipeline_or_assumptions() -> None:
    """Importing ``polaris_re.core`` must not pull the composition root — nor,
    through it, the ``assumptions`` layer — into ``sys.modules``.

    Keeping ``polaris_re.pipeline`` (and ``assumptions``) out of a bare
    ``import polaris_re.core`` preserves the ``core`` → (no) ``assumptions``
    layering at package-import time (CLAUDE.md §6).
    """
    result = _run_snippet(
        "import sys; import polaris_re.core; "
        "print('polaris_re.pipeline' in sys.modules, "
        "'polaris_re.assumptions.assumption_set' in sys.modules)"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False False", (
        "importing polaris_re.core dragged in the composition root and/or the "
        "assumptions layer, violating the CLAUDE.md §6 layering rule"
    )


def test_old_core_pipeline_path_is_gone() -> None:
    """``polaris_re.core.pipeline`` must no longer exist (ADR-156 relocation).

    Any surviving module at the old path would keep a ``core`` submodule
    importing ``assumptions`` and re-open the ADR-155 circular import. No
    backward-compat shim was left there (ADR-156, "no shim" decision).
    """
    result = _run_snippet(
        "import importlib.util; print(importlib.util.find_spec('polaris_re.core.pipeline'))"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "None", (
        "polaris_re.core.pipeline still resolves — the composition root was not "
        "fully relocated to polaris_re.pipeline (ADR-156)"
    )


def test_pipeline_symbols_reachable_at_canonical_path() -> None:
    """The pipeline symbols are importable from the new canonical module, and
    ``polaris_re.pipeline`` imports cleanly as the *first* import in a fresh
    interpreter (it is a root, so nothing needs to prime it)."""
    result = _run_snippet(
        "from polaris_re.pipeline import ("
        "DealConfig, LapseConfig, MortalityConfig, PipelineInputs, build_pipeline"
        "); print('ok')"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
