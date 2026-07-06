"""Execution guard for ``notebooks/05_validation_report.ipynb``.

The validation-report notebook (Validation & Benchmark Pack epic, Slice 3) is
the diligence-grade demonstration behind ``polaris benchmark``. Its code cells
embed the pass/fail contract as ``assert``s (every reference reproduced within
tolerance, all three categories represented, the full pack equal to the union of
the sub-packs), so *executing the notebook end to end* IS the verification — if
any reference drifts, the corresponding cell raises and this test fails.

Like the ALM / reserve-basis notebook guards, we execute the code cells directly
in one shared namespace rather than spinning up a Jupyter kernel (``nbclient`` is
not a project dependency). The notebook is magic-free and uses only the vendored
validation references, so ``exec`` reproduces a kernel run faithfully with no
external mortality CSVs required.
"""

from pathlib import Path

import nbformat
import pytest

NOTEBOOK = Path(__file__).resolve().parents[2] / "notebooks" / "05_validation_report.ipynb"


def _code_sources(path: Path) -> list[str]:
    nb = nbformat.read(path, as_version=4)
    return [cell.source for cell in nb.cells if cell.cell_type == "code"]


def test_notebook_file_exists() -> None:
    assert NOTEBOOK.is_file(), f"missing notebook: {NOTEBOOK}"


def test_notebook_has_code_cells() -> None:
    sources = _code_sources(NOTEBOOK)
    # Imports + report render + diligence assertions + per-case detail.
    assert len(sources) >= 3


def test_notebook_executes_and_validations_pass() -> None:
    """Run every code cell top to bottom; the embedded asserts are the checks.

    ``IPython.display`` is stubbed so the notebook's ``display(Markdown(...))``
    cell runs headless without importing IPython (not a project dependency).
    """
    import sys
    import types

    display_stub = types.ModuleType("IPython.display")
    display_stub.Markdown = lambda text: text  # type: ignore[attr-defined]
    display_stub.display = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    ipython_stub = types.ModuleType("IPython")
    ipython_stub.display = display_stub  # type: ignore[attr-defined]
    saved = {name: sys.modules.get(name) for name in ("IPython", "IPython.display")}
    sys.modules["IPython"] = ipython_stub
    sys.modules["IPython.display"] = display_stub
    try:
        namespace: dict[str, object] = {"__name__": "__validation_notebook__"}
        for index, source in enumerate(_code_sources(NOTEBOOK)):
            try:
                exec(compile(source, f"<notebook cell {index}>", "exec"), namespace)
            except Exception as exc:
                pytest.fail(
                    f"notebook cell {index} raised {type(exc).__name__}: {exc}\n"
                    f"--- cell source ---\n{source}"
                )
    finally:
        for name, mod in saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod

    # Spot-check the headline object the notebook builds actually ran the pack.
    report = namespace.get("report")
    assert report is not None, "notebook did not bind `report` (the full validation pack)"
    assert report.all_passed, "the validation report must pass end to end"
