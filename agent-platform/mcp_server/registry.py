"""Typed MCP registration without generated exec wrappers or silent failures."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from core.data_engine.engine import as_mcp_tool_spec


async def ping() -> str:
    """Check protocol connectivity."""
    return "pong"


def register_tools(server: FastMCP, runtime: Any = None) -> None:
    server.add_tool(ping)
    spec = as_mcp_tool_spec()
    server.add_tool(spec["func"], name=spec["name"], description=spec["description"])
    if runtime is not None:

        async def agent_invoke(
            message: str, session_id: str | None = None, agent_id: str = "default"
        ) -> str:
            """Invoke this operator's local agent platform. Reuse session_id for memory."""
            if not message.strip() or len(message) > 16000:
                raise ValueError("message must be non-empty and at most 16000 characters")
            sid, state = runtime.session("mcp-local", agent_id, session_id)
            answer = await runtime.invoke("mcp-local", agent_id, sid, state, message)
            import json

            return json.dumps({"output": answer, "session_id": sid}, ensure_ascii=False)

        server.add_tool(agent_invoke)
