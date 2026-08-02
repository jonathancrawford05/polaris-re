"""Structural tests for the CI ``perf`` job (perf-harness epic, Slice 3).

The ``perf`` job runs the head-vs-main performance-regression harness
(``scripts/perfbench.py``) on a single runner and gates the merge on its exit
status: a **structural / deterministic** regression (mismatched counts or output
fingerprint) is a hard delta and fails the job; the wall-time ratio and the
peak-MiB delta are advisory alerts that never change the exit status (the
maintainer's non-negotiable rule, 2026-07-12 — see ``docs/PLAN_perf_harness.md``
§2).

These are lint-style assertions on the workflow YAML so the wiring cannot be
silently deleted or regressed. They mirror ``tests/test_deploy/test_manifests.py``:
parse the file, assert the keys an operator (here: the merge gate) relies on. The
harness itself is exercised by ``tests/perf/`` and by running
``scripts/perfbench.py``; this file only pins the CI wiring.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _load_workflow() -> dict:
    with CI_WORKFLOW.open() as fh:
        return yaml.safe_load(fh)


def _perf_steps() -> list[dict]:
    return _load_workflow()["jobs"]["perf"]["steps"]


def test_ci_workflow_parses() -> None:
    doc = _load_workflow()
    assert "jobs" in doc
    assert isinstance(doc["jobs"], dict)


def test_perf_job_exists() -> None:
    jobs = _load_workflow()["jobs"]
    assert "perf" in jobs, "the CI workflow must define a 'perf' job (perf epic Slice 3)"


def test_perf_job_needs_lint() -> None:
    # Mirror the smoke job: gate behind lint so a formatting/lint failure short-circuits.
    perf = _load_workflow()["jobs"]["perf"]
    needs = perf["needs"]
    needs = [needs] if isinstance(needs, str) else needs
    assert "lint" in needs


def test_perf_job_runs_on_single_runner() -> None:
    perf = _load_workflow()["jobs"]["perf"]
    # A single-runner job (like smoke) — no build matrix that would multiply the
    # head-vs-main comparison across environments.
    assert "strategy" not in perf
    assert perf["runs-on"] == "ubuntu-latest"


def test_perf_job_only_on_pull_request() -> None:
    # Head-vs-main only makes sense on a PR; on a push to main the two would be
    # the same commit (a no-op self-compare with a fetch race). Gate to PR events.
    perf = _load_workflow()["jobs"]["perf"]
    assert perf["if"] == "github.event_name == 'pull_request'"


def test_perf_job_checks_out_full_history() -> None:
    # The git-worktree checkout of origin/main needs full history, not a shallow clone.
    checkout = next(
        s for s in _perf_steps() if str(s.get("uses", "")).startswith("actions/checkout")
    )
    assert checkout["with"]["fetch-depth"] == 0


def test_perf_job_materializes_origin_main() -> None:
    # An explicit fetch guarantees refs/remotes/origin/main resolves for the
    # worktree checkout regardless of the checkout action's default refspec.
    run_steps = " ".join(s.get("run", "") for s in _perf_steps())
    assert "refs/remotes/origin/main" in run_steps


def test_perf_job_runs_perfbench_against_origin_main() -> None:
    run_steps = " ".join(s.get("run", "") for s in _perf_steps())
    assert "scripts/perfbench.py" in run_steps
    assert "--ref origin/main" in run_steps
    assert "-o perf.json" in run_steps


def test_perf_job_does_not_generate_mortality_tables() -> None:
    # The probe uses the committed synthetic fixture, not the generated data/
    # tables — so no convert_soa_tables step is needed (keeps the job fast and
    # offline-safe). Guards against someone copy-pasting it from the test job.
    run_steps = " ".join(s.get("run", "") for s in _perf_steps())
    assert "convert_soa_tables" not in run_steps


def test_perf_job_uploads_perf_json_artifact() -> None:
    upload = next(
        s for s in _perf_steps() if str(s.get("uses", "")).startswith("actions/upload-artifact")
    )
    # Uploaded even when the gate fails, so a regression's evidence is inspectable.
    assert upload.get("if") == "always()"
    assert upload["with"]["path"] == "perf.json"
