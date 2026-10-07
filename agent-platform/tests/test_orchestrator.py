"""編排層測試：agent 構建/調用/串流、多會話記憶與 AgentRuntime 路由。"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import httpx
import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool, tool

from core.decision_review import DecisionReviewer, ReviewReport
from core.model_routing.profiles import ModelCatalog
from core.orchestrator.agent import ainvoke_agent, astream_agent, create_platform_agent
from core.orchestrator.memory import ConversationManager
from core.orchestrator.runtime import AgentRuntime, InvocationResult


class FakeToolChatModel(FakeListChatModel):
    """FakeListChatModel 預設不支援 bind_tools，覆寫為回傳自身。"""

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, Any]:
        return self


@tool
def alpha_search(query: str) -> str:
    """Search alpha records."""
    return query


@tool
def beta_lookup(query: str) -> str:
    """Look up beta records."""
    return query


def make_agent(responses: list[str] | None = None, tools: list[BaseTool] | None = None) -> Any:
    llm = FakeToolChatModel(responses=responses or ["fake answer"])
    return create_platform_agent(tools=tools if tools is not None else [], llm=llm)


async def test_create_platform_agent_with_explicit_tools() -> None:
    agent = make_agent(tools=[beta_lookup, alpha_search])
    result = await ainvoke_agent(agent, "hello")
    assert result == "fake answer"


async def test_create_platform_agent_with_empty_tools() -> None:
    agent = make_agent(tools=[])
    result = await ainvoke_agent(agent, "hello")
    assert result == "fake answer"


async def test_ainvoke_agent_accepts_str_message() -> None:
    agent = make_agent()
    result = await ainvoke_agent(agent, "純文字訊息")
    assert isinstance(result, str)
    assert result == "fake answer"


async def test_ainvoke_agent_accepts_message_list() -> None:
    agent = make_agent()
    history: list[Any] = [
        ("user", "first"),
        ("assistant", "ack"),
        ("user", "second"),
    ]
    result = await ainvoke_agent(agent, history)
    assert isinstance(result, str)
    assert result == "fake answer"


async def test_astream_agent_yields_text_deltas() -> None:
    agent = make_agent(responses=["streamed reply"])
    parts = [delta async for delta in astream_agent(agent, [("user", "hi")])]
    assert parts
    assert "".join(parts) == "streamed reply"


async def test_conversation_manager_multi_turn_memory() -> None:
    manager = ConversationManager(llm=FakeToolChatModel(responses=["r1", "r2"]))
    assert await manager.achat("hello", session_id="s1") == "r1"
    assert await manager.achat("again", session_id="s1") == "r2"
    history = manager.get_session_history("s1")
    assert [message.type for message in history.messages] == [
        "human",
        "ai",
        "human",
        "ai",
    ]


async def test_conversation_manager_session_isolation() -> None:
    manager = ConversationManager(llm=FakeToolChatModel(responses=["only"]))
    await manager.achat("one", session_id="a")
    await manager.achat("two", session_id="a")
    await manager.achat("other", session_id="b")
    assert set(manager.session_ids()) == {"a", "b"}
    assert len(manager.get_session_history("a").messages) == 4
    assert len(manager.get_session_history("b").messages) == 2


async def test_conversation_manager_clear() -> None:
    manager = ConversationManager(llm=FakeToolChatModel(responses=["x"]))
    await manager.achat("hi", session_id="a")
    await manager.achat("hi", session_id="b")
    manager.clear("a")
    assert manager.session_ids() == ["b"]
    assert len(manager.get_session_history("b").messages) == 2
    manager.clear("missing-session")
    assert manager.session_ids() == ["b"]


def make_demo_runtime(monkeypatch: pytest.MonkeyPatch) -> AgentRuntime:
    monkeypatch.setenv("AGENT_PLATFORM_DEMO", "1")
    return AgentRuntime()


def test_runtime_session_creation_and_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = make_demo_runtime(monkeypatch)
    sid_a, state_a = runtime.session("tenant-a", "chat", None)
    sid_b, state_b = runtime.session("tenant-b", "chat", None)
    assert sid_a and sid_b and sid_a != sid_b
    assert state_a is not state_b
    again_sid, again_state = runtime.session("tenant-a", "chat", sid_a)
    assert again_sid == sid_a
    assert again_state is state_a
    other_sid, other_state = runtime.session("tenant-a", "chat", None)
    assert other_sid != sid_a
    assert other_state is not state_a


def test_runtime_session_rejects_unknown_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = make_demo_runtime(monkeypatch)
    with pytest.raises(KeyError):
        runtime.session("tenant-a", "no-such-agent", None)


async def test_runtime_invoke_returns_route_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = make_demo_runtime(monkeypatch)
    sid, state = runtime.session("tenant-a", "chat", None)
    result = await runtime.invoke_with_route("tenant-a", "chat", sid, state, "你好，介紹一下平台")
    assert isinstance(result, InvocationResult)
    assert isinstance(result.output, str) and result.output
    assert result.route.model_id in runtime.catalog.profiles
    assert result.route.mode == "auto"
    assert result.route.decision_id
    assert len(state.history) == 2
    traces = runtime.route_traces("tenant-a")
    assert traces and traces[0]["status"] == "completed"
    assert traces[0]["model_id"] == result.route.model_id


async def test_runtime_explicit_model_request_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = make_demo_runtime(monkeypatch)
    sid, state = runtime.session("tenant-a", "chat", None)
    result = await runtime.invoke_with_route(
        "tenant-a", "chat", sid, state, "ping", model_id="demo-coder"
    )
    assert result.route.mode == "request"
    assert result.route.model_id == "demo-coder"


async def test_runtime_model_pin_and_restore_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = make_demo_runtime(monkeypatch)
    _, state = runtime.session("tenant-a", "chat", "pin-session")
    pinned = await runtime.switch_model("tenant-a", "chat", state, "demo-coder")
    assert pinned["model_id"] == "demo-coder"
    assert pinned["mode"] == "session"
    route = runtime.plan("tenant-a", "chat", state, "任何訊息")
    assert route.mode == "session"
    assert route.model_id == "demo-coder"
    restored = await runtime.switch_model("tenant-a", "chat", state, "auto")
    assert restored["model_id"] is None
    assert restored["mode"] == "auto"
    route = runtime.plan("tenant-a", "chat", state, "任何訊息")
    assert route.mode == "auto"
    assert route.model_id in runtime.catalog.profiles


async def test_runtime_switch_model_rejects_unknown_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = make_demo_runtime(monkeypatch)
    _, state = runtime.session("tenant-a", "chat", "bad-model")
    with pytest.raises(ValueError, match="Unknown or unavailable model"):
        await runtime.switch_model("tenant-a", "chat", state, "ghost-model")
    assert state.model_id is None


@pytest.mark.parametrize(
    ("jev_value", "judge_value", "expected"),
    [(0.9, 0.9, "approved"), (0.3, 0.2, "needs_revision")],
)
async def test_jev_and_distinct_model_form_consensus(
    jev_value: float, judge_value: float, expected: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/v1/systemone"
        assert set(payload["questions"]) == {"intent", "completeness", "clarity"}
        assert request.headers["Authorization"] == "Bearer fake-key"
        return httpx.Response(
            200,
            json={
                "model": "jev-mock",
                "answers": {
                    axis: {"type": "noul", "noul": jev_value}
                    for axis in ("intent", "completeness", "clarity")
                },
            },
        )

    reviewer = DecisionReviewer(
        ModelCatalog.demo(),
        lambda _: FakeListChatModel(
            responses=[
                json.dumps(dict.fromkeys(("intent", "completeness", "clarity"), judge_value))
            ]
        ),
        jev_key="fake-key",
        reviewer_models=("demo-coder",),
        http_client_factory=lambda **kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    report = await reviewer.review(
        tenant="tenant-a",
        producer_model="demo-fast",
        message="Explain",
        answer="Answer",
        task="general",
    )
    assert report.status == expected
    assert {opinion.source for opinion in report.opinions} == {"jev", "chat"}
    assert report.weak_axes == (
        [] if expected == "approved" else ["intent", "completeness", "clarity"]
    )


async def test_revision_does_not_reinvoke_agent_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = make_demo_runtime(monkeypatch)
    calls = 0
    reviews = 0

    async def fake_agent(*args: Any) -> object:
        return object()

    async def fake_invoke(*args: Any) -> str:
        nonlocal calls
        calls += 1
        return "draft"

    class Reviewer:
        async def review(self, **kwargs: Any) -> ReviewReport:
            nonlocal reviews
            reviews += 1
            return ReviewReport(
                status="needs_revision" if reviews == 1 else "approved",
                weak_axes=["completeness"] if reviews == 1 else [],
            )

    monkeypatch.setattr(runtime, "agent", fake_agent)
    monkeypatch.setattr("core.orchestrator.runtime.ainvoke_agent", fake_invoke)
    runtime.model_factory = lambda _: FakeListChatModel(responses=["revised"])
    runtime.reviewer = Reviewer()  # type: ignore[assignment]
    sid, state = runtime.session("tenant-a", "chat", None)
    result = await runtime.invoke_with_route("tenant-a", "chat", sid, state, "Explain", review=True)
    assert result.output == "revised"
    assert result.review is not None and result.review.revision_accepted
    assert calls == 1
    assert reviews == 2
    assert state.history[-1]["content"] == "revised"
