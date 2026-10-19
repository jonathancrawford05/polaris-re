"""``scripts/bam_local_run.py`` — the maintainer's real-cell Stage-B runner (ADR-260 amendment 5).

R-free: the Polaris half on a synthetic cell directory, the output whitelist, and a refusal
recorded as a result (a rank-deficient design is refused by name, not worked around)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "bam_local_run.py"


def _cell(tmp_path: Path, formula: str) -> Path:
    rng = np.random.default_rng(0)
    ages = np.repeat(np.arange(30, 70), 8)
    durs = np.tile(np.arange(1, 9), 40)
    expo = rng.uniform(5, 40, ages.size)
    deaths = rng.poisson(expo * np.exp(-5.5 + 0.04 * (ages - 30) - 0.03 * durs))
    smoker = np.where(rng.uniform(size=ages.size) < 0.3, "S", "NS")
    pl.DataFrame(
        {
            "attained_age": ages,
            "duration": durs,
            "smoker": smoker,
            "deaths": deaths,
            "log_exposure": np.log(expo),
        }
    ).write_csv(tmp_path / "cells.csv")
    (tmp_path / "spec.json").write_text(
        json.dumps(
            {
                "formula": formula,
                "family": "poisson",
                "weights": None,
                "select": False,
                "factors": {"smoker": ["NS", "S"]},
            }
        )
    )
    return tmp_path


def _run(cell: Path, env: dict[str, str] | None = None) -> dict[str, object]:
    out = cell / "out.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--cell", str(cell), "--repeats", "1", "--skip-r",
         "--out", str(out)],
        check=False, capture_output=True, text=True, cwd=REPO_ROOT, env=env,
    )  # fmt: skip
    # `check=True` raised CalledProcessError carrying stdout/stderr that pytest never prints, so a
    # Docker-only failure read as a bare "exit status 1" with no cause (PR #273). Spell it out.
    if proc.returncode != 0:
        raise AssertionError(
            f"{SCRIPT.name} exited {proc.returncode}\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    return json.loads(out.read_text())


def test_polaris_half_writes_whitelisted_scalars_only(tmp_path: Path) -> None:
    cell = _cell(
        tmp_path,
        'deaths ~ smoker + s(attained_age, bs="cr", k=8) + s(duration, bs="cr", k=5)'
        " + offset(log_exposure)",
    )
    res = _run(cell)
    assert res["cell"] == cell.name and res["n_rows"] == 320
    pol = res["polaris"]
    assert isinstance(pol, dict) and pol["converged"] is True and pol["ceiling_met"] is True
    # no row-level or level-name content
    assert "NS" not in json.dumps({k: v for k, v in res.items() if k != "machine"})


def test_a_bare_smooth_beside_a_factor_by_smooth_is_pivoted_and_fitted(tmp_path: Path) -> None:
    """ADR-256: the redundant direction is pivoted out (as bgam.fitd's Cholesky does) and the fit
    runs; it used to be refused."""
    cell = _cell(
        tmp_path,
        'deaths ~ smoker + s(attained_age, bs="cr", k=8) + s(attained_age, by=smoker, bs="cr",'
        " k=6) + offset(log_exposure)",
    )
    res = _run(cell)
    assert "status" not in res
    assert res["polaris"]["converged"] is True  # type: ignore[index]


def test_an_unsupported_family_is_recorded_as_a_refusal(tmp_path: Path) -> None:
    cell = _cell(tmp_path, 'deaths ~ smoker + s(attained_age, bs="cr", k=8) + offset(log_exposure)')
    spec = json.loads((cell / "spec.json").read_text())
    spec["family"] = "gaussian"
    (cell / "spec.json").write_text(json.dumps(spec))
    res = _run(cell)
    assert res["status"] == "refused"
    assert "gaussian" in str(res["refusal"]) or "not supported" in str(res["refusal"])


def test_the_runner_runs_where_git_is_absent(tmp_path: Path) -> None:
    """The runtime image is ``python:3.12-slim`` — no ``git``. ``subprocess(check=False)`` covers
    a non-zero exit, not a missing binary, so the commit lookup raised ``FileNotFoundError`` and
    every Docker run of this script exited 1 (PR #273). The sha degrades; the run does not."""
    cell = _cell(tmp_path, 'deaths ~ smoker + s(attained_age, bs="cr", k=8) + offset(log_exposure)')
    empty_bin = tmp_path / "bin"  # PATH with no git on it; python is invoked by absolute path
    empty_bin.mkdir()
    res = _run(cell, env={**os.environ, "PATH": str(empty_bin)})
    assert res["polaris_commit"] == "unknown"
    assert res["polaris"]["converged"] is True  # type: ignore[index]


def test_the_whitelist_refuses_an_unknown_key() -> None:
    import runpy

    mod = runpy.run_path(str(SCRIPT), run_name="not_main")
    with pytest.raises(SystemExit, match="non-whitelisted"):
        mod["_check_whitelist"]({"row_level_eta": [1.0]})
