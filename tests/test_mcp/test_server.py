"""Tests for the Polaris RE MCP server (``polaris_re.mcp.server``).

Slice 2 of the MCP-server epic wraps the shared service-layer entry point
:func:`polaris_re.services.pricing.run_price` in an in-process stdio MCP server.
These tests lock in the guarantees that make the server trustworthy:

1. **Parity** — ``polaris_price_block`` and ``polaris_price`` price through
   ``run_price`` with no second mapping, so their ``detail=true`` output is
   byte-identical to a direct ``run_price`` call *and* to the REST API.
2. **Read-only annotations** — every pricing tool advertises
   ``readOnly / idempotent = True``, ``destructive / openWorld = False``.
3. **Compact-by-default output** — ``detail=false`` clears the large per-year
   arrays; the ``summary`` headline is always present.
4. **Capabilities discovery** — the ``polaris://capabilities`` resource
   enumerates the priceable enums and sample-block ids.
5. **Actionable errors** — a bad inforce reference / product type / treaty type
   raises a tool error with guidance, not an opaque stack trace.
6. **Committed ``.mcp.json``** — valid JSON, launches ``polaris-mcp``, sets
   ``POLARIS_DATA_DIR`` (guards the zero-config clone experience from rotting).

All dates are pinned (ADR-074 guard — no wall-clock dependence).
"""

import asyncio
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from polaris_re.api.main import app
from polaris_re.mcp.server import (
    PriceBlockResult,
    build_price_request_from_block,
    main,
    mcp,
    polaris_price,
    polaris_price_block,
)
from polaris_re.services.pricing import PriceResponse, run_price

# Repo root = tests/test_mcp/<file> → parents[2]. The sample block resolves
# under $POLARIS_DATA_DIR; pin it to the repo's data/ dir so the tests do not
# depend on the caller's CWD or a pre-set env var.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "data"
_MCP_JSON = _REPO_ROOT / ".mcp.json"

# Golden block valuation date (the CSV's own embedded date).
_VDATE = date(2026, 4, 1)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _point_data_dir_at_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve the ``"golden"`` sample block regardless of the test CWD."""
    monkeypatch.setenv("POLARIS_DATA_DIR", str(_DATA_DIR))


# ---------------------------------------------------------------------------
# Server registration + schema + annotations
# ---------------------------------------------------------------------------


class TestServerRegistration:
    def test_two_pricing_tools_registered(self) -> None:
        names = {t.name for t in asyncio.run(mcp.list_tools())}
        assert {"polaris_price_block", "polaris_price"} <= names

    @pytest.mark.parametrize("tool_name", ["polaris_price_block", "polaris_price"])
    def test_read_only_annotations(self, tool_name: str) -> None:
        tool = next(t for t in asyncio.run(mcp.list_tools()) if t.name == tool_name)
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.idempotentHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.openWorldHint is False

    @pytest.mark.parametrize("tool_name", ["polaris_price_block", "polaris_price"])
    def test_tools_declare_structured_output(self, tool_name: str) -> None:
        tool = next(t for t in asyncio.run(mcp.list_tools()) if t.name == tool_name)
        assert tool.outputSchema is not None

    def test_valuation_date_required_on_block_tool(self) -> None:
        """ADR-074 guard: the block tool never defaults the valuation date."""
        tool = next(t for t in asyncio.run(mcp.list_tools()) if t.name == "polaris_price_block")
        assert "valuation_date" in tool.inputSchema.get("required", [])

    def test_price_tool_input_schema_reuses_price_request(self) -> None:
        """``polaris_price`` derives its schema from the PriceRequest contract —
        it exposes a ``policies`` array, not hand-copied fields."""
        tool = next(t for t in asyncio.run(mcp.list_tools()) if t.name == "polaris_price")
        assert "request" in tool.inputSchema["properties"]


# ---------------------------------------------------------------------------
# Parity: MCP tool == run_price == REST API
# ---------------------------------------------------------------------------


class TestPriceBlockParity:
    @pytest.mark.parametrize(
        "overrides",
        [
            {},
            {"treaty_type": "Coinsurance"},
            {"treaty_type": None},
            {"cession_pct": 0.5, "discount_rate": 0.05, "hurdle_rate": 0.12},
            {"capital_model": "licat"},
            {"product_type": "WHOLE_LIFE", "projection_horizon_years": 40},
        ],
    )
    def test_block_tool_detail_true_equals_run_price(self, overrides: dict[str, object]) -> None:
        """``detail=true`` output is byte-identical to a direct ``run_price``
        call built from the same inforce reference + params."""
        request = build_price_request_from_block(
            inforce="golden", valuation_date=_VDATE, **overrides
        )
        expected = run_price(request).model_dump()

        result = polaris_price_block(valuation_date=_VDATE, detail=True, **overrides)
        assert isinstance(result, PriceBlockResult)
        assert result.price.model_dump() == expected

    def test_block_tool_equals_rest_api(self) -> None:
        """The MCP tool and the REST API return the identical PriceResponse for
        the same assembled request — one engine path, no drift."""
        request = build_price_request_from_block(inforce="golden", valuation_date=_VDATE)

        mcp_json = polaris_price_block(valuation_date=_VDATE, detail=True).price.model_dump()

        response = client.post("/api/v1/price", json=request.model_dump(mode="json"))
        assert response.status_code == 200, response.text
        api_json = PriceResponse(**response.json()).model_dump()

        assert mcp_json == api_json

    def test_inline_price_tool_equals_run_price(self) -> None:
        """``polaris_price`` (inline policies) matches ``run_price`` at detail."""
        request = build_price_request_from_block(inforce="golden", valuation_date=_VDATE)
        expected = run_price(request).model_dump()
        result = polaris_price(request, detail=True)
        assert result.price.model_dump() == expected


# ---------------------------------------------------------------------------
# Compact-by-default output
# ---------------------------------------------------------------------------


class TestCompactOutput:
    def test_detail_false_clears_per_year_arrays(self) -> None:
        result = polaris_price_block(valuation_date=_VDATE, detail=False)
        assert result.price.profit_by_year == []
        assert result.price.reinsurer_profit_by_year == []

    def test_detail_true_keeps_per_year_arrays(self) -> None:
        result = polaris_price_block(valuation_date=_VDATE, detail=True)
        assert len(result.price.profit_by_year) > 0
        assert len(result.price.reinsurer_profit_by_year) > 0

    def test_summary_reports_headline_figures(self) -> None:
        result = polaris_price_block(valuation_date=_VDATE, capital_model="licat")
        assert "Cedant PV profit" in result.summary
        assert "Reinsurer PV profit" in result.summary
        # Peak capital only appears when a capital model was applied.
        assert "Peak cedant capital" in result.summary

    def test_summary_omits_capital_when_not_requested(self) -> None:
        result = polaris_price_block(valuation_date=_VDATE)
        assert "Peak cedant capital" not in result.summary

    def test_call_tool_returns_structured_and_text(self) -> None:
        """The manager path yields both a text block and structured content."""
        content, structured = asyncio.run(
            mcp.call_tool("polaris_price_block", {"valuation_date": "2026-04-01"})
        )
        assert content and content[0].text
        assert structured["summary"]
        assert structured["price"]["n_policies"] == 6


# ---------------------------------------------------------------------------
# Sample-block loading + re-valuation
# ---------------------------------------------------------------------------


class TestSampleBlockLoading:
    def test_golden_term_subset(self) -> None:
        request = build_price_request_from_block(inforce="golden", valuation_date=_VDATE)
        assert len(request.policies) == 6
        assert all(p.policy_id.startswith("GLD-T-") for p in request.policies)

    def test_golden_whole_life_subset(self) -> None:
        request = build_price_request_from_block(
            inforce="golden", valuation_date=_VDATE, product_type="WHOLE_LIFE"
        )
        assert len(request.policies) == 6
        assert all(p.policy_id.startswith("GLD-WL-") for p in request.policies)

    def test_revaluation_derives_age_and_duration_from_dates(self) -> None:
        """A later valuation date re-values the block: attained age and duration
        in force are re-derived from each policy's issue date, keeping the
        assembled block internally consistent (ADR-074)."""
        request = build_price_request_from_block(inforce="golden", valuation_date=date(2027, 4, 1))
        p = request.policies[0]
        # GLD-T-001 issued 2021-04-01, issue_age 30 → 6 years / 72 months later.
        assert p.valuation_date == date(2027, 4, 1)
        assert p.duration_inforce == 72
        assert p.attained_age == p.issue_age + 72 // 12

    def test_explicit_file_path_loads(self) -> None:
        path = _DATA_DIR / "qa" / "golden_inforce.csv"
        request = build_price_request_from_block(inforce=str(path), valuation_date=_VDATE)
        assert len(request.policies) == 6


# ---------------------------------------------------------------------------
# Actionable errors
# ---------------------------------------------------------------------------


class TestActionableErrors:
    def test_unknown_sample_or_file(self) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with pytest.raises(ToolError) as excinfo:
            build_price_request_from_block(inforce="not_a_block.csv", valuation_date=_VDATE)
        assert "golden" in str(excinfo.value)

    def test_unknown_product_type(self) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with pytest.raises(ToolError) as excinfo:
            build_price_request_from_block(
                inforce="golden", valuation_date=_VDATE, product_type="TERMINATOR"
            )
        assert "Valid:" in str(excinfo.value)

    def test_no_matching_product_in_block(self) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with pytest.raises(ToolError) as excinfo:
            build_price_request_from_block(
                inforce="golden", valuation_date=_VDATE, product_type="UL"
            )
        assert "contains" in str(excinfo.value)

    def test_unknown_treaty_maps_to_tool_error(self) -> None:
        """A domain failure inside ``run_price`` surfaces as a tool error with the
        original guidance (valid treaty types), not a raw traceback."""
        from mcp.server.fastmcp.exceptions import ToolError

        with pytest.raises(ToolError) as excinfo:
            polaris_price_block(valuation_date=_VDATE, treaty_type="NopeCoinsurance")
        assert "FWCoinsurance" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Capabilities resource
# ---------------------------------------------------------------------------


class TestCapabilitiesResource:
    def _read(self) -> dict[str, object]:
        contents = list(asyncio.run(mcp.read_resource("polaris://capabilities")))
        return json.loads(contents[0].content)

    def test_enumerates_priceable_enums(self) -> None:
        caps = self._read()
        assert caps["product_types"] == ["TERM", "WHOLE_LIFE", "UL"]
        assert caps["treaty_types"] == ["YRT", "Coinsurance", "Modco", "FWCoinsurance"]
        assert set(caps["capital_models"]) == {"licat", "rbc", "solvency2"}
        assert "NET_PREMIUM" in caps["reserve_bases"]

    def test_lists_sample_blocks(self) -> None:
        caps = self._read()
        assert "golden" in caps["sample_blocks"]

    def test_does_not_advertise_unpriceable_products(self) -> None:
        """DI / CI / ANNUITY exist in the enum but have no engine — not listed."""
        caps = self._read()
        assert "DI" not in caps["product_types"]
        assert "ANNUITY" not in caps["product_types"]


# ---------------------------------------------------------------------------
# Committed .mcp.json (zero-config clone)
# ---------------------------------------------------------------------------


class TestMcpJson:
    def test_valid_json(self) -> None:
        data = json.loads(_MCP_JSON.read_text())
        assert "mcpServers" in data

    def test_registers_polaris_mcp_command(self) -> None:
        server = json.loads(_MCP_JSON.read_text())["mcpServers"]["polaris"]
        assert server["command"] == "uv"
        assert "polaris-mcp" in server["args"]

    def test_sets_data_dir_env(self) -> None:
        server = json.loads(_MCP_JSON.read_text())["mcpServers"]["polaris"]
        assert "POLARIS_DATA_DIR" in server["env"]


def test_server_module_exposes_main_entry_point() -> None:
    """The ``polaris-mcp`` console script targets ``server:main``."""
    assert callable(main)
