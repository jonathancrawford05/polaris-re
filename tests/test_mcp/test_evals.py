"""Tests for the committed MCP eval set (``polaris_re.mcp.evals``).

Slice 4 of the MCP-server epic ships a 10-question eval set — realistic,
read-only, verifiable pricing Q&A against the ``golden`` sample block. These
tests run the set through the real ``mcp.call_tool`` / ``read_resource`` path and
assert every question's pinned answer, so the set is a green golden regression on
the whole MCP surface (any engine or tool-wiring drift flips an eval red with a
readable diff). They also guard the set's shape — ten questions covering all four
tools, the capabilities resource, and the actionable-error path.

All dates are pinned inside the eval definitions (ADR-074 guard — no wall-clock
dependence); the expected numbers are the epic's byte-identical golden values.
"""

from pathlib import Path

import pytest

from polaris_re.mcp.evals import EVAL_SET, MCPEval, run_eval

# Repo root = tests/test_mcp/<file> → parents[2]. The ``golden`` sample block
# resolves under $POLARIS_DATA_DIR; pin it to the repo's data/ dir so the eval
# runner does not depend on the caller's CWD or a pre-set env var.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "data"


@pytest.fixture(autouse=True)
def _point_data_dir_at_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve the ``"golden"`` sample block regardless of the test CWD."""
    monkeypatch.setenv("POLARIS_DATA_DIR", str(_DATA_DIR))


class TestEvalSetShape:
    def test_has_ten_questions(self) -> None:
        assert len(EVAL_SET) == 10

    def test_ids_are_unique(self) -> None:
        ids = [ev.id for ev in EVAL_SET]
        assert len(set(ids)) == len(ids)

    def test_every_eval_targets_exactly_one_surface(self) -> None:
        """An eval names a tool or a resource, never both / neither."""
        for ev in EVAL_SET:
            assert (ev.tool is None) != (ev.resource is None), ev.id

    def test_covers_all_four_tools_and_the_resource(self) -> None:
        tools = {ev.tool for ev in EVAL_SET if ev.tool is not None}
        assert tools == {
            "polaris_price_block",
            "polaris_run_scenario",
            "polaris_run_uq",
        }
        assert any(ev.resource == "polaris://capabilities" for ev in EVAL_SET)

    def test_includes_an_actionable_error_question(self) -> None:
        assert any(ev.expect_error_contains is not None for ev in EVAL_SET)

    def test_every_price_eval_pins_a_valuation_date(self) -> None:
        """ADR-074 guard: no eval leans on the wall clock."""
        for ev in EVAL_SET:
            if ev.tool is not None:
                assert ev.arguments.get("valuation_date"), ev.id


class TestEvalSetGreen:
    """Every committed eval must pass against the live engine."""

    @pytest.mark.parametrize("ev", EVAL_SET, ids=lambda ev: ev.id)
    def test_eval_passes(self, ev: MCPEval) -> None:
        result = run_eval(ev)
        assert result.passed, f"{ev.id} failed: {result.failures}"


class TestRunEvalMechanics:
    """The runner detects a wrong pinned answer (guards against silent drift)."""

    def test_wrong_expected_numeric_fails(self) -> None:
        good = next(ev for ev in EVAL_SET if ev.id == "price_golden_yrt90")
        tampered = good.model_copy(
            update={"expected_numeric": {"price.reinsurer_pv_profits": 999999.0}}
        )
        result = run_eval(tampered)
        assert not result.passed
        assert "price.reinsurer_pv_profits" in result.failures[0]

    def test_missing_error_is_reported(self) -> None:
        """An error question that does NOT raise is a failure, not a pass."""
        good = next(ev for ev in EVAL_SET if ev.id == "price_golden_yrt90")
        tampered = good.model_copy(update={"expect_error_contains": "never happens"})
        result = run_eval(tampered)
        assert not result.passed

    def test_float_in_expected_equals_is_rejected(self) -> None:
        """A float in ``expected_equals`` is a misuse (== on floats) — the runner
        flags it so a future eval author routes floats to ``expected_numeric``
        instead of silently introducing a float-equality path."""
        good = next(ev for ev in EVAL_SET if ev.id == "price_golden_yrt90")
        tampered = good.model_copy(
            update={
                "expected_numeric": {},
                "expected_equals": {"price.reinsurer_pv_profits": 51.530862},
            }
        )
        result = run_eval(tampered)
        assert not result.passed
        assert "expected_numeric" in result.failures[0]

    def test_no_eval_puts_a_float_in_expected_equals(self) -> None:
        """The shipped set never uses a float in ``expected_equals`` (floats go to
        ``expected_numeric``) — enforce the convention the guard protects."""
        for ev in EVAL_SET:
            for path, value in ev.expected_equals.items():
                assert not isinstance(value, float), f"{ev.id}:{path} is a float"
