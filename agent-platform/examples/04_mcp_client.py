"""示例 04：原生 MCP 协议互操作 —— stdio Client 调用平台 MCP Server。

演示目的：
    以官方 mcp SDK 的 stdio client 通过子进程方式启动
    `python -m mcp_server.server --transport stdio`，完成初始化握手、
    枚举 7 个工具及其 inputSchema，并实际调用 ping 与 route_preview，
    验证 MCP 协议层的工具即插即用能力。

运行方式（无需真实 LLM key，demo 模式自动启用 Mock 模型目录）：
    python examples/04_mcp_client.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _step(title: str) -> None:
    print(f"\n=== {title} ===")


def _server_parameters() -> StdioServerParameters:
    env = dict(os.environ)
    env["AGENT_PLATFORM_DEMO"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server", "--transport", "stdio"],
        env=env,
        cwd=str(PROJECT_ROOT),
    )


def _print_tools(tools: list[Any]) -> None:
    print(f"共发现 {len(tools)} 个工具：")
    for spec in tools:
        print(f"\n[{spec.name}]")
        print(f"  描述: {spec.description}")
        print("  inputSchema:")
        schema = json.dumps(spec.inputSchema, ensure_ascii=False, indent=4)
        for line in schema.splitlines():
            print(f"    {line}")


async def _call_text(session: ClientSession, name: str, arguments: dict[str, Any]) -> str:
    result = await session.call_tool(name, arguments)
    if result.isError:
        raise RuntimeError(f"工具 {name} 调用失败: {result.content}")
    return "\n".join(item.text for item in result.content if item.type == "text")


async def main() -> None:
    _step("步骤 1/5：以子进程方式启动 MCP Server（stdio 传输）")
    params = _server_parameters()
    print(f"命令: {params.command} {' '.join(params.args)}")
    print("子进程环境: AGENT_PLATFORM_DEMO=1（demo 模式，无需真实 LLM key）")

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            _step("步骤 2/5：初始化握手（initialize）")
            init_result = await session.initialize()
            print(f"服务器名称: {init_result.serverInfo.name}")
            print(f"服务器版本: {init_result.serverInfo.version}")
            print(f"协议版本: {init_result.protocolVersion}")

            _step("步骤 3/5：枚举工具（list_tools）")
            page = await session.list_tools()
            _print_tools(page.tools)

            _step("步骤 4/5：调用 ping（协议连通性检查）")
            pong = await _call_text(session, "ping", {})
            print(f"ping -> {pong}")

            _step("步骤 5/5：调用 route_preview（任务分类 + 模型路由预览）")
            preview = await _call_text(
                session,
                "route_preview",
                {"message": "帮我用 Python 写一个快速排序并解释时间复杂度"},
            )
            decision = json.loads(preview)
            print(json.dumps(decision, ensure_ascii=False, indent=2))

    _step("完成：会话与子进程已优雅关闭")


if __name__ == "__main__":
    asyncio.run(main())
