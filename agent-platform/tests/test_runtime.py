import asyncio
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from core.orchestrator.runtime import AgentRuntime


@pytest.mark.asyncio
async def test_concurrent_same_session_requests_are_serialized() -> None:
    runtime = AgentRuntime()
    runtime.configs["chat"]["llm"] = FakeListChatModel(responses=["first", "second"])
    sid, state = runtime.session("tenant", "chat", "same")
    answers = await asyncio.gather(
        runtime.invoke("tenant", "chat", sid, state, "q1"),
        runtime.invoke("tenant", "chat", sid, state, "q2"),
    )
    assert answers == ["first", "second"]
    assert [m["content"] for m in state.history] == ["q1", "first", "q2", "second"]


def test_session_capacity_eviction_and_busy_capacity() -> None:
    runtime = AgentRuntime(max_sessions=2)
    runtime.session("tenant", "chat", "old")
    runtime.session("tenant", "chat", "second")
    runtime.session("tenant", "chat", "third")
    assert len(runtime.sessions) == 2
    assert ("tenant", "chat", "old") not in runtime.sessions


@pytest.mark.asyncio
async def test_cancelled_stream_does_not_commit_partial_answer() -> None:
    runtime = AgentRuntime()
    _, state = runtime.session("t", "chat", "s")
    stream = runtime.stream("t", "chat", state, "x" * 100)
    assert await anext(stream)
    await stream.aclose()
    assert state.history == []
    assert not state.lock.locked()


@pytest.mark.asyncio
async def test_private_tenant_indexes_never_fall_back_to_shared_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "secret-a.txt").write_text("alpha-private-only", encoding="utf-8")
    (b / "secret-b.txt").write_text("beta-private-only", encoding="utf-8")
    import json

    monkeypatch.setenv("AGENT_PLATFORM_TENANT_DOCS", json.dumps({"a": str(a), "b": str(b)}))
    runtime = AgentRuntime()
    for tenant, own, other in [
        ("a", "alpha-private-only", "beta-private-only"),
        ("b", "beta-private-only", "alpha-private-only"),
    ]:
        sid, state = runtime.session(tenant, "default", "same")
        answer = await runtime.invoke(tenant, "default", sid, state, "private")
        assert own in answer and other not in answer
    with pytest.raises(RuntimeError, match="No knowledge directory"):
        await runtime.agent("unconfigured", "default")
