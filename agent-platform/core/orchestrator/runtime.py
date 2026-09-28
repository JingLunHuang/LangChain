"""Shared API/MCP runtime with tenant/agent/session isolation and request locks."""

from __future__ import annotations

import asyncio
import json
import os
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from time import monotonic
from typing import Any
from uuid import uuid4

from core.cache_optimizer.optimizer import ContextOptimizer
from core.data_engine.engine import DEFAULT_DOCS_PATH, abuild_query_engine, as_langchain_tool
from core.orchestrator.agent import (
    DEFAULT_SYSTEM_PROMPT,
    ainvoke_agent,
    astream_agent,
    create_platform_agent,
)


@dataclass
class Session:
    history: list[dict[str, str]] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    touched: float = field(default_factory=monotonic)


class AgentRuntime:
    def __init__(self, *, max_sessions: int = 256, ttl: float = 3600) -> None:
        self.configs: dict[str, dict[str, Any]] = {
            "default": {
                "description": "Knowledge assistant",
                "system_prefix": DEFAULT_SYSTEM_PROMPT,
            },
            "chat": {
                "description": "Conversation assistant",
                "system_prefix": DEFAULT_SYSTEM_PROMPT,
                "tools": [],
            },
        }
        self.external_tools: list[Any] = []
        self.sessions: OrderedDict[tuple[str, str, str], Session] = OrderedDict()
        self.agents: dict[tuple[str, str], Any] = {}
        self.agent_lock = asyncio.Lock()
        self.max_sessions = max_sessions
        self.ttl = ttl
        self.tenant_docs = json.loads(os.getenv("AGENT_PLATFORM_TENANT_DOCS", "{}"))

    def resolve(self, tenant: str, agent_id: str) -> dict[str, Any]:
        config = self.configs.get(agent_id)
        if config is None or (config.get("tenant_ids") and tenant not in config["tenant_ids"]):
            raise KeyError("Unknown or unavailable agent")
        return config

    def session(self, tenant: str, agent_id: str, session_id: str | None) -> tuple[str, Session]:
        self.resolve(tenant, agent_id)
        now = monotonic()
        for key, state in list(self.sessions.items()):
            if now - state.touched > self.ttl and not state.lock.locked():
                self.sessions.pop(key)
        sid = session_id or str(uuid4())
        key = (tenant, agent_id, sid)
        if key not in self.sessions:
            if len(self.sessions) >= self.max_sessions:
                idle = next((k for k, v in self.sessions.items() if not v.lock.locked()), None)
                if idle is None:
                    raise RuntimeError("Session capacity reached")
                self.sessions.pop(idle)
            self.sessions[key] = Session()
        self.sessions.move_to_end(key)
        state = self.sessions[key]
        state.touched = now
        return sid, state

    async def agent(self, tenant: str, agent_id: str) -> Any:
        key = (tenant, agent_id)
        config = self.resolve(tenant, agent_id)
        async with self.agent_lock:
            if key not in self.agents:
                tools = config.get("tools")
                if tools is None:
                    # No shared data directory fallback for a configured private tenant map.
                    if self.tenant_docs and tenant not in self.tenant_docs:
                        raise RuntimeError("No knowledge directory configured for this tenant")
                    path = self.tenant_docs.get(
                        tenant,
                        os.getenv("AGENT_PLATFORM_DOCS_PATH") or str(DEFAULT_DOCS_PATH),
                    )
                    engine = await abuild_query_engine(path)
                    tools = [as_langchain_tool(engine)]
                self.agents[key] = create_platform_agent(
                    tools=[*tools, *self.external_tools],
                    llm=config.get("llm"),
                    system_prompt=None,
                )
            return self.agents[key]

    async def prepare(self, config: dict[str, Any], state: Session, message: str) -> list[Any]:
        optimizer = ContextOptimizer(
            system_prefix=config.get("system_prefix", DEFAULT_SYSTEM_PROMPT),
            max_tokens=config.get("max_tokens", 4096),
            few_shot_examples=config.get("few_shot_examples"),
            summary_llm=config.get("summary_llm"),
        )
        return await optimizer.optimize_request(
            state.history + [{"role": "user", "content": message}]
        )

    @staticmethod
    def commit(state: Session, message: str, answer: str) -> None:
        state.history.extend(
            [{"role": "user", "content": message}, {"role": "assistant", "content": answer}]
        )
        # Keep original text for 64 completed turns; summarize only request copies.
        state.history = state.history[-128:]
        state.touched = monotonic()

    async def invoke(
        self, tenant: str, agent_id: str, sid: str, state: Session, message: str
    ) -> str:
        async with state.lock:
            messages = await self.prepare(self.resolve(tenant, agent_id), state, message)
            agent = await self.agent(tenant, agent_id)
            answer = await ainvoke_agent(agent, messages)
            self.commit(state, message, answer)
            return answer

    async def stream(
        self,
        tenant: str,
        agent_id: str,
        state: Session,
        message: str,
    ) -> AsyncIterator[str]:
        async with state.lock:
            messages = await self.prepare(self.resolve(tenant, agent_id), state, message)
            agent = await self.agent(tenant, agent_id)
            parts = []
            async for delta in astream_agent(agent, messages):
                parts.append(delta)
                yield delta
            self.commit(state, message, "".join(parts))
