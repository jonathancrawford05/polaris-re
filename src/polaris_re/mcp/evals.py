"""
Polaris RE — MCP server evaluation set.

A committed, verifiable eval set for the MCP server (MCP-server epic Slice 4;
``docs/PLAN_mcp_server.md``). Each :class:`MCPEval` is a realistic, read-only
pricing question an actuary would ask an agent, paired with the tool call that
answers it and the **pinned, deterministic** answer the engine returns. The set
is exercised by ``tests/test_mcp/test_evals.py`` (parametrized, green in CI), so
it doubles as a golden regression on the MCP surface: any drift in the engine or
the tool wiring flips an eval red with a readable diff rather than a silent
number change.

Why a declarative set rather than ad-hoc assertions:

* **Inspectable.** :data:`EVAL_SET` is importable data — the ten questions and
  their expected answers can be listed, rendered, or replayed without reading the
  test file. A future MCP eval CLI or docs page reuses it directly.
* **Path-addressed expectations.** An expectation is a dotted path into the
  tool's structured result (e.g. ``price.reinsurer_pv_profits``) plus the value,
  compared with a relative tolerance (floats) or exact equality (ints / strings /
  lists / ``None``). No bespoke assertion code per question.
* **Read-only + reproducible.** Every question pins an explicit ``valuation_date``
  (ADR-074 guard — never ``date.today()``); ``polaris_run_uq`` also pins a seed.
  The engine mutates nothing, so the set is safe to replay against any host.

The pinned numbers are the golden QA block priced with the tools' documented
flat-assumption defaults (``flat_qx=0.003`` / ``flat_lapse=0.05``); the epic's
byte-identical discipline keeps them stable.
"""

import asyncio
import json
import math

from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

from polaris_re.core.base import PolarisBaseModel
from polaris_re.mcp.server import mcp

__all__ = [
    "EVAL_SET",
    "EvalResult",
    "MCPEval",
    "run_eval",
    "run_eval_set",
]


class MCPEval(PolarisBaseModel):
    """One realistic, verifiable MCP pricing question.

    Exactly one of ``tool`` / ``resource`` is set. Expectations are dotted paths
    into the structured result: ``expected_numeric`` compares floats with
    ``rel_tol``; ``expected_equals`` compares ints / strings / lists / ``None``
    exactly (**never floats** — a float belongs in ``expected_numeric``, since
    ``==`` on floats is unreliable; ``run_eval`` flags a float in
    ``expected_equals`` as a failure). ``summary_contains`` asserts substrings of a
    tool result's one-line ``summary``. An error question sets
    ``expect_error_contains`` — the tool call must raise a :class:`ToolError` whose
    message contains that guidance.
    """

    id: str
    question: str
    tool: str | None = None
    resource: str | None = None
    arguments: dict[str, object] = Field(default_factory=dict)
    expected_numeric: dict[str, float] = Field(default_factory=dict)
    expected_equals: dict[str, object] = Field(default_factory=dict)
    summary_contains: list[str] = Field(default_factory=list)
    expect_error_contains: str | None = None
    rel_tol: float = 1e-6
    note: str = ""


class EvalResult(PolarisBaseModel):
    """Outcome of running one :class:`MCPEval`: pass plus any mismatch details."""

    eval_id: str
    passed: bool
    failures: list[str] = Field(default_factory=list)


def _dig(obj: object, path: str) -> object:
    """Resolve a dotted ``path`` into nested mappings/lists, ``None`` if absent.

    A numeric segment indexes a list (e.g. ``scenario.scenarios.1.pv_profits``
    reaches the second scenario); every other segment is a mapping key.
    """
    current = obj
    for key in path.split("."):
        if isinstance(current, list):
            if not key.isdigit() or int(key) >= len(current):
                return None
            current = current[int(key)]
        elif isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def _invoke(ev: MCPEval) -> dict[str, object]:
    """Execute the eval's tool or resource, returning its structured result.

    Tool results are the tool's ``structuredContent`` (e.g. ``{"summary": ...,
    "price": {...}}``); resource results are the parsed JSON body.
    """
    if ev.resource is not None:
        contents = list(asyncio.run(mcp.read_resource(ev.resource)))
        return json.loads(contents[0].content)
    assert ev.tool is not None, f"eval {ev.id!r} has neither a tool nor a resource"
    _content, structured = asyncio.run(mcp.call_tool(ev.tool, dict(ev.arguments)))
    return structured


def run_eval(ev: MCPEval) -> EvalResult:
    """Run one eval and report pass/fail with readable mismatch descriptions."""
    if ev.expect_error_contains is not None:
        try:
            _invoke(ev)
        except ToolError as exc:
            if ev.expect_error_contains in str(exc):
                return EvalResult(eval_id=ev.id, passed=True)
            return EvalResult(
                eval_id=ev.id,
                passed=False,
                failures=[
                    f"error message {str(exc)!r} does not contain {ev.expect_error_contains!r}"
                ],
            )
        return EvalResult(
            eval_id=ev.id,
            passed=False,
            failures=[f"expected a ToolError containing {ev.expect_error_contains!r}, none raised"],
        )

    structured = _invoke(ev)
    failures: list[str] = []

    for path, expected in ev.expected_numeric.items():
        got = _dig(structured, path)
        if not isinstance(got, (int, float)) or isinstance(got, bool):
            failures.append(f"{path}: expected numeric {expected}, got {got!r}")
        elif not math.isclose(got, expected, rel_tol=ev.rel_tol, abs_tol=1e-9):
            failures.append(f"{path}: expected {expected}, got {got}")

    for path, expected in ev.expected_equals.items():
        # expected_equals is for EXACT matches (ints / strings / lists / None). A
        # float here would be an `==` comparison, which CLAUDE.md forbids — floats
        # belong in expected_numeric (checked with math.isclose). Guard so a future
        # eval author cannot silently introduce a float-equality path. (bool is an
        # int subclass, not a float, so True/False stay valid here.)
        if isinstance(expected, float):
            failures.append(
                f"{path}: float {expected!r} in expected_equals — put floats in "
                "expected_numeric (math.isclose), never expected_equals (== on floats)"
            )
            continue
        got = _dig(structured, path)
        if got != expected:
            failures.append(f"{path}: expected {expected!r}, got {got!r}")

    if ev.summary_contains:
        summary = _dig(structured, "summary")
        if not isinstance(summary, str):
            failures.append(f"summary: expected a string, got {summary!r}")
        else:
            for needle in ev.summary_contains:
                if needle not in summary:
                    failures.append(f"summary does not contain {needle!r}")

    return EvalResult(eval_id=ev.id, passed=not failures, failures=failures)


def run_eval_set(evals: list[MCPEval] | None = None) -> list[EvalResult]:
    """Run the whole eval set (default :data:`EVAL_SET`) and return each result."""
    return [run_eval(ev) for ev in (EVAL_SET if evals is None else evals)]


# Golden QA block valuation date (the CSV's own embedded date). Pinned on every
# question so a quote is reproducible (ADR-074 — never ``date.today()``).
_VDATE = "2026-04-01"


# The ten realistic, read-only, verifiable pricing questions. Expected values are
# the golden QA block priced with the tools' documented flat-assumption defaults;
# the MCP epic's byte-identical discipline keeps them stable.
EVAL_SET: list[MCPEval] = [
    MCPEval(
        id="price_golden_yrt90",
        question=(
            "Price the 'golden' sample block as a YRT treaty at 90% cession, 6% "
            "discount, valuation 2026-04-01. How many policies, and what is the "
            "reinsurer PV profit?"
        ),
        tool="polaris_price_block",
        arguments={"valuation_date": _VDATE},
        expected_equals={"price.n_policies": 6, "price.reserve_basis": "NET_PREMIUM"},
        expected_numeric={
            "price.pv_profits": -26939.212549,
            "price.reinsurer_pv_profits": 51.530862,
        },
        summary_contains=["6 policies", "Reinsurer PV profit"],
        note="Default deal params: YRT 90% cession, 6% discount, TERM subset.",
    ),
    MCPEval(
        id="price_golden_gross_only",
        question=(
            "Price the 'golden' block with no treaty (gross only), valuation "
            "2026-04-01. What is the cedant PV profit?"
        ),
        tool="polaris_price_block",
        arguments={"valuation_date": _VDATE, "treaty_type": None},
        expected_numeric={"price.pv_profits": -26887.681623},
        note="treaty_type=null → gross-only; no ceded cash flows.",
    ),
    MCPEval(
        id="price_golden_coinsurance_50",
        question=(
            "Price the 'golden' block on a 50% coinsurance treaty, valuation "
            "2026-04-01. What is the reinsurer PV profit?"
        ),
        tool="polaris_price_block",
        arguments={
            "valuation_date": _VDATE,
            "treaty_type": "Coinsurance",
            "cession_pct": 0.5,
        },
        expected_numeric={"price.reinsurer_pv_profits": -13443.840811},
        note="Coinsurance is proportional: 50% cession halves the gross result.",
    ),
    MCPEval(
        id="price_golden_licat_capital",
        question=(
            "Price the 'golden' block YRT 90% with the LICAT capital model, "
            "valuation 2026-04-01. What is the peak required capital?"
        ),
        tool="polaris_price_block",
        arguments={"valuation_date": _VDATE, "capital_model": "licat"},
        expected_numeric={"price.peak_capital": 49489.477699},
        summary_contains=["Peak cedant capital"],
        note="capital_model set → peak_capital + return-on-capital populated.",
    ),
    MCPEval(
        id="price_golden_whole_life",
        question=(
            "Price the whole-life policies in the 'golden' block YRT 90%, "
            "valuation 2026-04-01. How many policies and what is the cedant PV "
            "profit?"
        ),
        tool="polaris_price_block",
        arguments={"valuation_date": _VDATE, "product_type": "WHOLE_LIFE"},
        expected_equals={"price.n_policies": 6},
        expected_numeric={
            "price.pv_profits": 2934746.073118,
            "price.reinsurer_pv_profits": 31888.295237,
        },
        note="A single run prices one product engine; the WHOLE_LIFE subset.",
    ),
    MCPEval(
        id="scenario_golden_mortality_shock",
        question=(
            "Stress the 'golden' block YRT 90% under the standard scenario set "
            "(reinsurer view), valuation 2026-04-01. What is the reinsurer PV "
            "profit in the base run versus a +10% mortality shock?"
        ),
        tool="polaris_run_scenario",
        arguments={"valuation_date": _VDATE},
        expected_equals={
            "scenario.perspective": "reinsurer",
            "scenario.n_scenarios": 6,
            "scenario.scenarios.0.scenario_name": "BASE",
            "scenario.scenarios.1.scenario_name": "MORT_110",
        },
        expected_numeric={
            "scenario.scenarios.0.pv_profits": 51.530862,
            "scenario.scenarios.1.pv_profits": -5164.122782,
        },
        note="BASE 52 → MORT_110 -5,164: a +10% mortality shock flips the deal.",
    ),
    MCPEval(
        id="uq_golden_seed42",
        question=(
            "Run Monte-Carlo UQ on the 'golden' block YRT 90% (reinsurer view), "
            "200 sims, seed 42, valuation 2026-04-01. What is the P5/P50/P95 PV "
            "profit band and the 95% VaR?"
        ),
        tool="polaris_run_uq",
        arguments={"valuation_date": _VDATE, "seed": 42, "n_scenarios": 200},
        expected_equals={"uq.perspective": "reinsurer", "uq.n_scenarios": 200, "uq.seed": 42},
        expected_numeric={
            "uq.p5_pv_profit": -8556.736895,
            "uq.p50_pv_profit": 321.082852,
            "uq.p95_pv_profit": 6697.014279,
            "uq.var_95": -8556.736895,
            "uq.cvar_95": -10986.882199,
        },
        note="Seeded LogNormal/Normal sampling → a reproducible downside band.",
    ),
    MCPEval(
        id="uq_golden_seed42_reproducible",
        question=(
            "Re-run the same seeded UQ (seed 42, 200 sims) on the 'golden' block. "
            "Is the P50 PV profit identical to the prior run?"
        ),
        tool="polaris_run_uq",
        arguments={"valuation_date": _VDATE, "seed": 42, "n_scenarios": 200},
        expected_numeric={"uq.p50_pv_profit": 321.082852},
        note="Determinism: the same seed reproduces the same distribution (ADR-074).",
    ),
    MCPEval(
        id="capabilities_enumerated",
        question=("What product types and treaty types can the Polaris RE MCP server price?"),
        resource="polaris://capabilities",
        expected_equals={
            "product_types": ["TERM", "WHOLE_LIFE", "UL"],
            "treaty_types": ["YRT", "Coinsurance", "Modco", "FWCoinsurance"],
        },
        note="The capabilities resource lets an agent discover valid enums.",
    ),
    MCPEval(
        id="error_bad_inforce_path",
        question=(
            "Price the block at './does_not_exist.csv', valuation 2026-04-01. "
            "(The path is wrong — the tool should say so, not crash.)"
        ),
        tool="polaris_price_block",
        arguments={"valuation_date": _VDATE, "inforce": "./does_not_exist.csv"},
        expect_error_contains="golden",
        note="A bad inforce reference must return actionable guidance, not a stack trace.",
    ),
]
