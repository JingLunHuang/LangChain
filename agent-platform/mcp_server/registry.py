"""MCP 工具公開同一份模型策略與執行核心。"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from core.data_engine.engine import as_mcp_tool_spec
from core.model_routing.profiles import Preference, TaskType
from core.model_routing.requests import InvokeRequest, ReviewRequest, SwitchRequest


async def ping() -> str:
    """檢查協議連線。"""
    return "pong"


def register_tools(server: FastMCP, runtime: Any = None) -> None:
    server.add_tool(ping)
    spec = as_mcp_tool_spec()
    server.add_tool(spec["func"], name=spec["name"], description=spec["description"])
    if runtime is None:
        return

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
        request = InvokeRequest(
            message=message,
            session_id=session_id,
            agent_id=agent_id,
            model_id=model_id,
            preference=preference,
            task=task,
            max_cost_tier=max_cost_tier,
        )
        sid, state = runtime.session("mcp-local", request.agent_id, request.session_id)
        async with state.lock:
            route = runtime.plan(
                "mcp-local",
                request.agent_id,
                state,
                request.message,
                **request.routing(),
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
        request = SwitchRequest(
            session_id=session_id,
            agent_id=agent_id,
            model_id=model_id,
            preference=preference,
            max_cost_tier=max_cost_tier,
        )
        sid, state = runtime.session("mcp-local", request.agent_id, request.session_id)
        result = await runtime.switch_model(
            "mcp-local",
            request.agent_id,
            state,
            request.model_id,
            preference=request.preference,
            max_cost_tier=request.max_cost_tier,
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
        review: bool = False,
    ) -> str:
        """依任務自動選模或手動指定模型，執行 Agent 並回傳路由決策。"""
        request = InvokeRequest(
            message=message,
            session_id=session_id,
            agent_id=agent_id,
            model_id=model_id,
            preference=preference,
            task=task,
            max_cost_tier=max_cost_tier,
            review=review,
        )
        sid, state = runtime.session("mcp-local", request.agent_id, request.session_id)
        result = await runtime.invoke_with_route(
            "mcp-local",
            request.agent_id,
            sid,
            state,
            request.message,
            review=request.review,
            **request.routing(),
        )
        return json.dumps(
            {
                "output": result.output,
                "session_id": sid,
                "route": result.route.model_dump(),
                "review": result.review.model_dump() if result.review else None,
            },
            ensure_ascii=False,
        )

    async def agent_review(
        message: str,
        answer: str,
        producer_model: str = "external",
        agent_id: str = "default",
        task: TaskType = "general",
    ) -> str:
        """以 Jev 與不同模型的獨立意見評估現有回答，不產生新回答。"""
        request = ReviewRequest(
            message=message,
            answer=answer,
            producer_model=producer_model,
            agent_id=agent_id,
            task=task,
        )
        runtime.resolve("mcp-local", request.agent_id)
        report = await runtime.reviewer.review(
            tenant="mcp-local",
            producer_model=request.producer_model,
            message=request.message,
            answer=request.answer,
            task=request.task,
        )
        return report.model_dump_json()

    async def routing_traces(limit: int = 50) -> str:
        """查看最近路由的模型、任務、狀態與耗時，不包含對話原文。"""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be 1..100")
        return json.dumps(runtime.route_traces("mcp-local", limit), ensure_ascii=False)

    for tool in (
        model_catalog,
        route_preview,
        model_switch,
        agent_invoke,
        agent_review,
        routing_traces,
    ):
        server.add_tool(tool)
