"""Execution guard for ``notebooks/02_reserve_basis_comparison.ipynb``.

The reserve-basis notebook demonstrates the profit signature across reserve
bases and — as of the Reserve-Basis Exactness epic, Slice 2 — CRVM valued on a
*prescribed* statutory valuation table via ``AssumptionSet.valuation_mortality``
(ADR-125). The new section embeds its reconciliation as assertions (a
conservative prescribed table must move the CRVM profit; ``NET_PREMIUM`` must
ignore the slot), so *executing the notebook end to end* IS the verification.

Like the ALM notebook guard, we execute the code cells directly in one shared
namespace rather than spinning up a Jupyter kernel (``nbclient`` is not a project
dependency). The notebook is magic-free, so ``exec`` reproduces a kernel run. It
uses only synthetic tables, so no external mortality CSVs are required.
"""

from pathlib import Path

import nbformat
import pytest

NOTEBOOK = Path(__file__).resolve().parents[2] / "notebooks" / "02_reserve_basis_comparison.ipynb"


def _code_sources(path: Path) -> list[str]:
    nb = nbformat.read(path, as_version=4)
    return [cell.source for cell in nb.cells if cell.cell_type == "code"]


def test_notebook_file_exists() -> None:
    assert NOTEBOOK.is_file(), f"missing notebook: {NOTEBOOK}"


def test_notebook_executes_and_validations_pass() -> None:
    """Run every code cell top to bottom; the embedded asserts are the checks."""
    namespace: dict[str, object] = {"__name__": "__reserve_basis_notebook__"}
    for index, source in enumerate(_code_sources(NOTEBOOK)):
        try:
            exec(compile(source, f"<notebook cell {index}>", "exec"), namespace)
        except Exception as exc:
            pytest.fail(
                f"notebook cell {index} raised {type(exc).__name__}: {exc}\n"
                f"--- cell source ---\n{source}"
            )

    # The prescribed-valuation section must have bound the statutory assumption
    # set with the valuation table attached (defensive: ensures the new cell ran).
    assumptions_stat = namespace.get("assumptions_stat")
    assert assumptions_stat is not None, "notebook did not bind `assumptions_stat`"
    assert assumptions_stat.valuation_mortality is not None, (
        "the statutory assumption set must carry a prescribed valuation table"
    )
