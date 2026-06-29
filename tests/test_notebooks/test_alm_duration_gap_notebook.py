"""Execution guard for ``notebooks/04_alm_duration_gap.ipynb``.

The ALM validation notebook (Asset/ALM epic, Slice 4b-4) is the end-to-end
demonstration behind the duration-gap surfaces. Its code cells embed the
closed-form reconciliations as ``np.testing.assert_allclose`` / ``assert``
checks (reserve run-off telescoping to the held reserve, zero-coupon
duration/convexity, the duration-primitive consistency check, a zero-gap matched
block, and the immunisation inequality), so *executing the notebook end to end*
IS the verification — if any reconciliation drifts, the corresponding cell
raises and this test fails.

``nbclient`` / ``nbconvert`` are not project dependencies, so rather than spin up
a Jupyter kernel we execute the code cells directly in one shared namespace
(exactly how a kernel runs them top to bottom). The notebook is deliberately
magic-free so ``exec`` reproduces a kernel run faithfully.
"""

from pathlib import Path

import nbformat
import pytest

NOTEBOOK = Path(__file__).resolve().parents[2] / "notebooks" / "04_alm_duration_gap.ipynb"


def _code_sources(path: Path) -> list[str]:
    nb = nbformat.read(path, as_version=4)
    return [cell.source for cell in nb.cells if cell.cell_type == "code"]


def test_notebook_file_exists() -> None:
    assert NOTEBOOK.is_file(), f"missing notebook: {NOTEBOOK}"


def test_notebook_has_code_cells() -> None:
    sources = _code_sources(NOTEBOOK)
    # Imports + the seasoned block + treaty + portfolio + dual gap + four
    # validations + immunisation: comfortably more than a handful of cells.
    assert len(sources) >= 8


def test_notebook_executes_and_validations_pass() -> None:
    """Run every code cell top to bottom; the embedded asserts are the checks."""
    namespace: dict[str, object] = {"__name__": "__alm_notebook__"}
    for index, source in enumerate(_code_sources(NOTEBOOK)):
        try:
            exec(compile(source, f"<notebook cell {index}>", "exec"), namespace)
        except Exception as exc:
            pytest.fail(
                f"notebook cell {index} raised {type(exc).__name__}: {exc}\n"
                f"--- cell source ---\n{source}"
            )

    # Spot-check that the headline objects the notebook builds are present and
    # carry the reinsurer-view gap the surfaces report (defensive: ensures the
    # notebook actually ran the ALM path, not just imported cleanly).
    dual = namespace.get("dual")
    assert dual is not None, "notebook did not bind `dual` (the dual duration gap)"
    assert dual.reinsurer is not None, "coinsurance block should define the reinsurer-view gap"
    assert dual.cedant is not None, "coinsurance block should define the cedant-view gap"
