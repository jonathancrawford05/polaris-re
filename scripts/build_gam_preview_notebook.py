#!/usr/bin/env python3
"""Build ``notebooks/gam_parity_preview.ipynb`` (preview slice P5) and execute its code.

The notebook runs the worked example of ``docs/GAM_USER_GUIDE.md``. Cells are executed
in-process, in order, and their printed output stored, so the committed notebook carries
real outputs; ``tests/test_gam/test_guide.py`` re-executes every code cell.

Usage: build_gam_preview_notebook.py [output.ipynb]
"""

import contextlib
import io
import sys
from pathlib import Path

import nbformat

_CELLS: list[tuple[str, str]] = [
    (
        "markdown",
        "# Polaris GAM — parity preview, worked example\n\n"
        "**Preview.** `polaris_re.gam` fits a *verified subset* of `mgcv`'s formula language "
        "by REML. It is not `mgcv`-compatible in general: see `docs/GAM_USER_GUIDE.md` for "
        "the subset, the refusal list, the oracle version and the gates, and "
        "`docs/GAM_PARITY_REPORT.md` for the generated comparison against `mgcv`. This "
        "notebook is the guide's §2, and the same formula and CSVs are fitted by `mgcv` in "
        "CI (report §4).",
    ),
    (
        "code",
        "from polaris_re.gam import GUIDE_FAMILY, GUIDE_FORMULA, gam, load_guide_example\n\n"
        "train, new = load_guide_example()\n"
        "print(train.shape, new.shape)\n"
        "print(GUIDE_FORMULA)\n"
        "train.head()",
    ),
    ("markdown", "## Fit\n\nOne call, no solver options; the search is deterministic Newton REML."),
    ("code", "fit = gam(GUIDE_FORMULA, train, GUIDE_FAMILY)\nprint(fit.converged)"),
    ("markdown", "## Summary\n\nNo p-values: they are outside the verified subset."),
    ("code", "print(fit.summary())"),
    (
        "markdown",
        "## Predict at new rows, with standard errors\n\n`unconditional=True` adds the "
        "smoothing-parameter-uncertainty correction (`Vc`).",
    ),
    (
        "code",
        'link, link_se = fit.predict(new, "link", se_fit=True)\n'
        'rate, rate_se = fit.predict(new, "response", se_fit=True)\n'
        '_, link_se_c = fit.predict(new, "link", se_fit=True, unconditional=True)\n'
        "for i in range(3):\n"
        '    print(f"row {i}: rate {rate[i]:.4f}  se {rate_se[i]:.4f}  '
        'link se {link_se[i]:.4f}  (unconditional {link_se_c[i]:.4f})")',
    ),
    (
        "markdown",
        "## What is refused\n\nAnything outside the verified subset is refused by name — "
        "here a bare `s(x)`, whose `mgcv` default basis (`tp`) is not yet verified.",
    ),
    (
        "code",
        "from polaris_re.core.exceptions import PolarisValidationError\n\n"
        "try:\n"
        '    gam("deaths ~ s(age)", train, "quasipoisson")\n'
        "except PolarisValidationError as exc:\n"
        "    print(exc)",
    ),
]


def build(out: Path) -> None:
    nb = nbformat.v4.new_notebook()
    scope: dict[str, object] = {}
    count = 0
    for kind, source in _CELLS:
        if kind == "markdown":
            nb.cells.append(nbformat.v4.new_markdown_cell(source))
            continue
        count += 1
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exec(compile(source, f"<cell {count}>", "exec"), scope)
        cell = nbformat.v4.new_code_cell(source)
        cell.execution_count = count
        text = buffer.getvalue()
        cell.outputs = [nbformat.v4.new_output("stream", name="stdout", text=text)] if text else []
        nb.cells.append(cell)
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    nb.metadata["language_info"] = {"name": "python", "version": "3.12"}
    nbformat.validate(nb)
    nbformat.write(nb, out)
    print(f"Wrote {out} ({count} code cells executed)")


def code_cells() -> list[str]:
    """The code cell sources, for the test that re-executes them."""
    return [source for kind, source in _CELLS if kind == "code"]


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("notebooks/gam_parity_preview.ipynb"))
