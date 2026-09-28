"""MCP 工具公開同一份模型策略與執行核心。"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from core.data_engine.engine import as_mcp_tool_spec
from core.model_routing.profiles import Preference, TaskType


async def ping() -> str:
    """檢查協議連線。"""
    return "pong"


def register_tools(server: FastMCP, runtime: Any = None) -> None:
    server.add_tool(ping)
    spec = as_mcp_tool_spec()
    server.add_tool(spec["func"], name=spec["name"], description=spec["description"])
    if runtime is None:
        return

    def validate_message(message: str) -> None:
        if not message.strip() or len(message) > 16000:
            raise ValueError("message must be non-empty and at most 16000 characters")

    async def model_catalog(agent_id: str = "default") -> str:
        """列出操作者可用的模型能力與設定狀態，不回傳金鑰或端點。"""
        config = runtime.resolve("mcp-local", agent_id)
        return json.dumps(
            runtime.catalog.public("mcp-local", config.get("model_ids")), ensure_ascii=False
        )

    async def route_preview(
        message: str,
        session_id: str | None = None,
        agent_id: str = "default",
        model_id: str | None = None,
        preference: Preference | None = None,
        task: TaskType | None = None,
        max_cost_tier: int | None = None,
    ) -> str:
        """預覽任務辨識、候選模型與選擇理由，不呼叫模型。"""
        validate_message(message)
        if max_cost_tier is not None and not 1 <= max_cost_tier <= 3:
            raise ValueError("max_cost_tier must be 1..3")
        sid, state = runtime.session("mcp-local", agent_id, session_id)
        async with state.lock:
            route = runtime.plan(
                "mcp-local",
                agent_id,
                state,
                message,
                model_id=model_id,
                preference=preference,
                task_hint=task,
                max_cost_tier=max_cost_tier,
            )
        return json.dumps({"session_id": sid, **route.model_dump()}, ensure_ascii=False)

    async def model_switch(
        session_id: str,
        model_id: str | None = None,
        agent_id: str = "default",
        preference: Preference | None = None,
        max_cost_tier: int | None = None,
    ) -> str:
        """設定對話固定模型；model_id 為 auto 或 null 時恢復自動選模，保留歷史。"""
        if max_cost_tier is not None and not 1 <= max_cost_tier <= 3:
            raise ValueError("max_cost_tier must be 1..3")
        sid, state = runtime.session("mcp-local", agent_id, session_id)
        result = await runtime.switch_model(
            "mcp-local",
            agent_id,
            state,
            model_id,
            preference=preference,
            max_cost_tier=max_cost_tier,
        )
        return json.dumps({"session_id": sid, **result}, ensure_ascii=False)

    async def agent_invoke(
        message: str,
        session_id: str | None = None,
        agent_id: str = "default",
        model_id: str | None = None,
        preference: Preference | None = None,
        task: TaskType | None = None,
        max_cost_tier: int | None = None,
    ) -> str:
        """依任務自動選模或手動指定模型，執行 Agent 並回傳路由決策。"""
        validate_message(message)
        if max_cost_tier is not None and not 1 <= max_cost_tier <= 3:
            raise ValueError("max_cost_tier must be 1..3")
        sid, state = runtime.session("mcp-local", agent_id, session_id)
        result = await runtime.invoke_with_route(
            "mcp-local",
            agent_id,
            sid,
            state,
            message,
            model_id=model_id,
            preference=preference,
            task_hint=task,
            max_cost_tier=max_cost_tier,
        )
        return json.dumps(
            {"output": result.output, "session_id": sid, "route": result.route.model_dump()},
            ensure_ascii=False,
        )

    async def routing_traces(limit: int = 50) -> str:
        """查看最近路由的模型、任務、狀態與耗時，不包含對話原文。"""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be 1..100")
        return json.dumps(runtime.route_traces("mcp-local", limit), ensure_ascii=False)

    for tool in (model_catalog, route_preview, model_switch, agent_invoke, routing_traces):
        server.add_tool(tool)
