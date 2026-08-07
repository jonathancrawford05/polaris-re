"""Execution guard for ``notebooks/06_experience_gam_diligence.ipynb``.

The diligence notebook is the visual/quantitative companion to
``docs/MEASUREMENT_experience_gam_hmd.md`` and ``..._ilec.md``. Its code cells
embed every quantitative claim those documents make as ``assert`` /
``np.testing.assert_allclose`` checks against the **committed** reports under
``docs/measurements/`` — so *executing the notebook end to end* IS the
verification. If a number in the prose drifts from the report it was drawn from,
or a re-run changes a finding, a cell raises and this test fails.

That coupling is the point: the measurement documents are prose, and prose does
not fail CI on its own.

The notebook reads **only committed aggregates**, never licensed data, so it runs
for anyone who clones the repository — no HMD account, no SOA terms acceptance.

``nbclient`` / ``nbconvert`` are not project dependencies, so rather than spin up
a Jupyter kernel the code cells are executed directly in one shared namespace,
exactly how a kernel runs them top to bottom. The notebook is deliberately
magic-free so ``exec`` reproduces a kernel run faithfully.
"""

import json
from pathlib import Path

import nbformat
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = REPO_ROOT / "notebooks" / "06_experience_gam_diligence.ipynb"
MEASUREMENTS = REPO_ROOT / "docs" / "measurements"

EXPECTED_REPORTS = (
    "experience_gam_hmd_usa",
    "experience_gam_hmd_gbrtenw",
    "experience_gam_ilec",
    "experience_gam_ilec_duration_banded",
)


def _code_sources(path: Path) -> list[str]:
    nb = nbformat.read(path, as_version=4)
    return [cell.source for cell in nb.cells if cell.cell_type == "code"]


def test_notebook_file_exists() -> None:
    assert NOTEBOOK.is_file(), f"missing notebook: {NOTEBOOK}"


def test_notebook_has_code_cells() -> None:
    sources = _code_sources(NOTEBOOK)
    # Setup + fit quality + slowdown + old-age divergence + duration effect +
    # decomposition + insured-vs-population.
    assert len(sources) >= 6


def test_notebook_is_magic_free() -> None:
    """``exec`` only reproduces a kernel faithfully without magics or shell escapes."""
    for source in _code_sources(NOTEBOOK):
        for line in source.splitlines():
            stripped = line.strip()
            assert not stripped.startswith(("%", "!")), f"magic/shell line: {stripped!r}"


@pytest.mark.parametrize("name", EXPECTED_REPORTS)
def test_committed_report_is_present_and_parses(name: str) -> None:
    """The notebook's inputs are committed findings, not licensed data."""
    path = MEASUREMENTS / f"{name}.json"
    assert path.is_file(), f"missing committed report: {path}"
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == 1
    # Findings only: basenames, never a path that could carry a home directory.
    assert "/" not in json.dumps(payload["inputs"])


EXPECTED_DEGRADED: list[str] = []
"""Sections the notebook cannot verify because a committed report predates the
feature they read.

Pinned, not merely tolerated. The notebook's contract is that executing it checks
the prose, so a section that prints a message instead of asserting carries no
coverage — and left unpinned, that silence is indistinguishable from a section
that ran. This list fails in **both** directions: a new gap fails, and a gap that
closes fails too, forcing the expectation to be updated when the maintainer's
re-run lands (PR #185 round-2 review [P2]).

Empty as of 2026-08-06: the maintainer's re-run populated ``standardised_ae``,
and clearing this list is the change that test forced — which is the mechanism
working exactly as intended.
"""


def _execute_notebook() -> dict[str, object]:
    namespace: dict[str, object] = {}
    for index, source in enumerate(_code_sources(NOTEBOOK)):
        try:
            exec(source, namespace)
        except Exception as exc:  # pragma: no cover - failure path is the signal
            raise AssertionError(
                f"notebook cell {index} raised {type(exc).__name__}: {exc}"
            ) from exc
    return namespace


def test_notebook_executes_end_to_end() -> None:
    """The real check: every embedded assertion holds against the committed reports."""
    _execute_notebook()


def test_degraded_sections_are_exactly_the_expected_ones() -> None:
    """Coverage cannot quietly shrink — or quietly grow — without this failing."""
    namespace = _execute_notebook()
    assert namespace["DEGRADED"] == EXPECTED_DEGRADED, (
        "the notebook's unverified sections changed. If a maintainer re-run "
        "populated a section, remove it from EXPECTED_DEGRADED; if a new gap "
        "appeared, the notebook is asserting less than it claims."
    )


@pytest.mark.skipif(
    not (REPO_ROOT / ".dockerignore").is_file(),
    reason=(
        "build-time inputs; absent inside the image by design. This guard is about "
        "the REPO's build configuration, so it has nothing to assert from within a "
        "container built from it."
    ),
)
def test_measurements_ship_into_the_docker_image() -> None:
    """The runtime image runs the test suite, so whatever the suite reads must be
    in the image.

    ``docs/`` was excluded wholesale by ``.dockerignore``, which meant the reports
    this module reads were absent and the Docker job went red while every other
    check passed (2026-08-05). Asserted structurally because the failure is
    invisible without a Docker daemon — the same coupling `data/qa/`, `deploy/`,
    `.github/workflows/` and `.mcp.json` each needed.

    Skipped inside the image, and the skip is the point rather than an evasion:
    ``Dockerfile`` and ``.dockerignore`` are build-time inputs that correctly do
    not ship. Asserting on them from within a container is the very mistake this
    test exists to catch — which is how it caught itself (2026-08-06).
    """
    ignore = (REPO_ROOT / ".dockerignore").read_text().splitlines()
    ignore = [line.strip() for line in ignore if line.strip() and not line.startswith("#")]
    assert "!docs/measurements/**" in ignore, ".dockerignore must re-include the reports"
    # ...and the blanket exclusion must be the /* form, or the negation cannot win.
    assert "docs/*" in ignore and "docs/" not in ignore

    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    assert "COPY docs/measurements/" in dockerfile, "Dockerfile must copy the reports"


def test_notebook_reaches_the_headline_findings() -> None:
    """Guard against the notebook quietly losing a section it is meant to carry."""
    text = NOTEBOOK.read_text()
    for claim in (
        "midlife collapse replicates independently",
        "insured outpace the population at midlife",
        "largest single-age duration effect",
        "not evidence that assumptions are sound",
    ):
        assert claim in text, f"notebook no longer states: {claim!r}"
