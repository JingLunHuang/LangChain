"""編排層測試：使用 fake LLM，不產生真實 API 呼叫。"""

import asyncio
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import tool

from core.orchestrator.agent import ainvoke_agent, create_platform_agent
from core.orchestrator.memory import ConversationManager


class ToolAwareFakeChatModel(FakeListChatModel):
    """支持 bind_tools 的 fake LLM，用於替代真實 ChatTongyi。"""

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Runnable:
        return self


@tool
def echo(text: str) -> str:
    """原樣回傳輸入文字。"""
    return text


def test_create_platform_agent_with_explicit_tools_and_llm() -> None:
    fake_llm = ToolAwareFakeChatModel(responses=["ok"])
    agent = create_platform_agent(tools=[echo], llm=fake_llm)
    assert agent is not None
    assert hasattr(agent, "ainvoke")


def test_create_platform_agent_without_tools_falls_back_safely() -> None:
    fake_llm = ToolAwareFakeChatModel(responses=["ok"])
    agent = create_platform_agent(tools=None, llm=fake_llm)
    assert agent is not None


def test_create_platform_agent_empty_tools_falls_back_safely() -> None:
    fake_llm = ToolAwareFakeChatModel(responses=["ok"])
    agent = create_platform_agent(tools=[], llm=fake_llm)
    assert agent is not None


def test_ainvoke_agent_returns_last_message_content() -> None:
    async def run() -> str:
        fake_llm = ToolAwareFakeChatModel(responses=["你好，世界"])
        agent = create_platform_agent(tools=[echo], llm=fake_llm)
        return await ainvoke_agent(agent, "打個招呼")

    assert asyncio.run(run()) == "你好，世界"


def test_conversation_manager_multi_turn_same_session() -> None:
    async def run() -> tuple[str, str, int]:
        fake_llm = FakeListChatModel(responses=["回覆一", "回覆二"])
        manager = ConversationManager(llm=fake_llm)
        first = await manager.achat("第一條", session_id="s1")
        second = await manager.achat("第二條", session_id="s1")
        return first, second, len(manager.get_session_history("s1").messages)

    first, second, history_len = asyncio.run(run())
    assert first == "回覆一"
    assert second == "回覆二"
    assert history_len == 4


def test_conversation_manager_session_isolation() -> None:
    async def run() -> ConversationManager:
        fake_llm = FakeListChatModel(responses=["a1", "b1", "a2"])
        manager = ConversationManager(llm=fake_llm)
        await manager.achat("會話A第一條", session_id="a")
        await manager.achat("會話B第一條", session_id="b")
        await manager.achat("會話A第二條", session_id="a")
        return manager

    manager = asyncio.run(run())
    assert len(manager.get_session_history("a").messages) == 4
    assert len(manager.get_session_history("b").messages) == 2
    assert set(manager.session_ids()) == {"a", "b"}


def test_conversation_manager_clear_session() -> None:
    async def run() -> ConversationManager:
        fake_llm = FakeListChatModel(responses=["x"])
        manager = ConversationManager(llm=fake_llm)
        await manager.achat("hi", session_id="temp")
        return manager

    manager = asyncio.run(run())
    manager.clear("temp")
    assert "temp" not in manager.session_ids()
    assert len(manager.get_session_history("temp").messages) == 0
