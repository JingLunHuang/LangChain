"""Offline MCP handshake, retrieval, and schema-preserving LangChain adapter demo."""

from __future__ import annotations

import asyncio
import sys

from mcp_server.client import MCPConnection, as_langchain_tools, connect


async def main() -> None:
    config = MCPConnection(
        name="knowledge",
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        env={"AGENT_PLATFORM_DEMO": "1"},
    )
    async with connect(config) as session:
        tools = await as_langchain_tools(session, config.name)
        print("Available tools:", [t.name for t in tools])
        retrieval = next(t for t in tools if t.name == "knowledge__hybrid_retrieve")
        print(await retrieval.ainvoke({"query": "What is KV cache?"}))


if __name__ == "__main__":
    asyncio.run(main())
