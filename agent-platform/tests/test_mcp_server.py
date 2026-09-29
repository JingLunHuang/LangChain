"""協議層測試：MCP Server 工具、資源、提示與 in-process 客戶端握手。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

from mcp_server import registry
from mcp_server.client import as_langchain_tools
from mcp_server.server import SERVER_NAME, create_server

EXPECTED_TOOLS = {
    "ping",
    "hybrid_retrieve",
    "model_catalog",
    "route_preview",
    "model_switch",
    "agent_invoke",
    "routing_traces",
}


@pytest.fixture(autouse=True)
def demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_DEMO", "1")


def _text(result: Any) -> str:
    content = result[0] if isinstance(result, tuple) else result
    return "\n".join(block.text for block in content if getattr(block, "type", None) == "text")


async def _tool_names(server: FastMCP) -> set[str]:
    return {tool.name for tool in await server.list_tools()}


async def test_create_server_instantiates() -> None:
    server = create_server()
    assert isinstance(server, FastMCP)
    assert server.name == SERVER_NAME


async def test_list_tools_contains_all_seven() -> None:
    server = create_server()
    assert await _tool_names(server) == EXPECTED_TOOLS


async def test_ping_returns_pong() -> None:
    server = create_server()
    assert _text(await server.call_tool("ping", {})) == "pong"


async def test_route_preview_returns_decision_structure() -> None:
    server = create_server()
    payload = json.loads(_text(await server.call_tool("route_preview", {"message": "你好"})))
    assert payload["session_id"]
    assert payload["decision_id"]
    assert payload["model_id"].startswith("demo-")
    assert payload["provider"] == "demo"
    assert payload["mode"] == "auto"
    assert payload["task"]["task"] in {"general", "coding", "reasoning", "writing", "knowledge"}
    assert isinstance(payload["candidates"], list) and payload["candidates"]
    assert isinstance(payload["reasons"], list) and payload["reasons"]


async def test_resources_and_prompts_include_extension_examples() -> None:
    server = create_server()
    resources = await server.list_resources()
    assert "info://server" in {str(resource.uri) for resource in resources}
    content = await server.read_resource("info://server")
    text = "".join(getattr(item, "content", "") for item in content)
    assert SERVER_NAME in text
    prompts = await server.list_prompts()
    assert "diagnose" in {prompt.name for prompt in prompts}
    rendered = await server.get_prompt("diagnose", {"target": "retrieval"})
    messages = getattr(rendered, "messages", rendered)
    assert "retrieval" in json.dumps(
        [message.model_dump(mode="json") for message in messages], ensure_ascii=False
    )


async def test_registry_surfaces_data_engine_failure_after_ping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_spec() -> dict[str, Any]:
        raise ImportError("No module named 'core.data_engine'")

    monkeypatch.setattr(registry, "as_mcp_tool_spec", broken_spec)
    server = FastMCP("partial")
    with pytest.raises(ImportError, match="core.data_engine"):
        registry.register_tools(server)
    names = await _tool_names(server)
    assert "ping" in names
    assert "hybrid_retrieve" not in names


async def test_in_process_client_handshake_and_langchain_adapters() -> None:
    from mcp.shared.memory import create_connected_server_and_client_session

    server = create_server()
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        page = await session.list_tools()
        assert {tool.name for tool in page.tools} == EXPECTED_TOOLS

        result = await session.call_tool("ping", {})
        assert not result.isError
        assert _text(result.content) == "pong"

        tools = await as_langchain_tools(session, "omni")
        assert [tool.name for tool in tools] == sorted(f"omni__{name}" for name in EXPECTED_TOOLS)
        ping = next(tool for tool in tools if tool.name == "omni__ping")
        assert await ping.ainvoke({}) == "pong"
