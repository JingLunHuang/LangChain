"""Actual MCP SDK handshakes on stdio, SSE and Streamable HTTP."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from mcp_server.client import MCPConnection, as_langchain_tools, connect

ROOT = Path(__file__).resolve().parents[1]
HTTP_TEST_KEY = "test-mcp-key"


@asynccontextmanager
async def running_server(transport: str):
    if transport == "stdio":
        yield MCPConnection(
            name="test",
            command=sys.executable,
            args=["-m", "mcp_server.server"],
            env={"AGENT_PLATFORM_DEMO": "1"},
        )
        return
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    environment = {**os.environ, "AGENT_PLATFORM_DEMO": "1", "PLATFORM_MCP_KEY": HTTP_TEST_KEY}
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "mcp_server.server",
        "--transport",
        transport,
        "--port",
        str(port),
        cwd=ROOT,
        env=environment,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        path = "sse" if transport == "sse" else "mcp"
        url = f"http://127.0.0.1:{port}/{path}"
        async with httpx.AsyncClient(trust_env=False) as client:
            for _ in range(100):
                if process.returncode is not None:
                    raise RuntimeError("MCP subprocess exited before readiness")
                try:
                    response = await client.get(url)
                    if response.status_code == 401:
                        break
                except httpx.ConnectError:
                    pass
                await asyncio.sleep(0.1)
            else:
                raise RuntimeError("MCP subprocess failed readiness check")
        yield MCPConnection(
            name="test", transport=transport, url=url, headers={"X-API-Key": HTTP_TEST_KEY}
        )
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()


@pytest.mark.parametrize("transport", ["stdio", "sse", "streamable-http"])
@pytest.mark.asyncio
async def test_mcp_handshake_tools_resources_prompts_and_agent(transport: str) -> None:
    async with running_server(transport) as config, connect(config) as session:
        listed = await session.list_tools()
        assert {t.name for t in listed.tools} == {"ping", "hybrid_retrieve", "agent_invoke"}
        result = await session.call_tool("ping", {})
        assert not result.isError and result.content[0].text == "pong"
        schema = next(t for t in listed.tools if t.name == "hybrid_retrieve").inputSchema
        assert "query" in schema["properties"]
        assert "docs_path" not in schema["properties"]
        tools = await as_langchain_tools(session, "test")
        retrieval = next(t for t in tools if t.name == "test__hybrid_retrieve")
        payload = json.loads(await retrieval.ainvoke({"query": "KV cache PagedAttention"}))
        assert "cache.md" in [s["file"] for s in payload["sources"]]
        failed = await session.call_tool("hybrid_retrieve", {"query": ""})
        assert failed.isError
        resources = await session.list_resources()
        assert any(str(r.uri) == "info://server" for r in resources.resources)
        resource = await session.read_resource("info://server")
        assert "agent-platform" in resource.contents[0].text
        prompt = await session.get_prompt("diagnose", {"target": "example.com"})
        assert "example.com" in prompt.messages[0].content.text
        answer = await session.call_tool("agent_invoke", {"message": "hello", "agent_id": "chat"})
        assert not answer.isError
        assert json.loads(answer.content[0].text)["session_id"]
