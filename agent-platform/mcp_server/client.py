"""Native MCP clients and schema-preserving LangChain adapters."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from langchain_core.tools import StructuredTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from pydantic import BaseModel, Field


class MCPConnection(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    transport: Literal["stdio", "sse", "streamable-http"] = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


@asynccontextmanager
async def connect(config: MCPConnection) -> AsyncIterator[ClientSession]:
    if config.transport == "stdio":
        if not config.command:
            raise ValueError("stdio requires command")
        transport = stdio_client(
            StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env,
            )
        )
    else:
        if not config.url:
            raise ValueError("HTTP transport requires url")
        factory = sse_client if config.transport == "sse" else streamablehttp_client
        transport = factory(config.url, headers=config.headers)
    async with transport as streams, ClientSession(streams[0], streams[1]) as session:
        await session.initialize()
        yield session


def _adapter(session: ClientSession, spec: Any, namespace: str) -> StructuredTool:
    async def invoke(**arguments: Any) -> str:
        result = await session.call_tool(spec.name, arguments)
        if result.isError:
            raise RuntimeError(f"MCP tool {spec.name} returned an error")
        return "\n".join(item.text for item in result.content if item.type == "text")

    return StructuredTool.from_function(
        coroutine=invoke,
        name=f"{namespace}__{spec.name}",
        description=spec.description or spec.name,
        args_schema=spec.inputSchema,
        infer_schema=False,
    )


async def as_langchain_tools(session: ClientSession, namespace: str) -> list[StructuredTool]:
    tools = []
    cursor = None
    while True:
        page = await session.list_tools(cursor=cursor)
        tools.extend(_adapter(session, spec, namespace) for spec in page.tools)
        cursor = page.nextCursor
        if not cursor:
            return sorted(tools, key=lambda tool: tool.name)
