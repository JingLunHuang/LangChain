import copy
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from core.cache_optimizer.optimizer import (
    SUMMARY_MARKER,
    ContextBudgetError,
    ContextOptimizer,
    estimate_tokens,
)
from core.data_engine.compression import summarize_texts


@pytest.mark.asyncio
async def test_prefix_idempotent_and_input_unchanged() -> None:
    opt = ContextOptimizer(
        "固定前綴",
        few_shot_examples=[
            {"role": "user", "content": "example"},
            {"role": "assistant", "content": "answer"},
        ],
    )
    original = [{"role": "user", "content": "new request"}]
    snapshot = copy.deepcopy(original)
    first = await opt.optimize(original)
    second = await opt.optimize(first)
    assert first == second
    assert original == snapshot
    assert json.dumps(first[:3]) == json.dumps(opt.build_prefix())


@pytest.mark.asyncio
async def test_real_compression_respects_cjk_budget_and_latest_question() -> None:
    opt = ContextOptimizer("fixed", max_tokens=360, keep_recent=2)
    history = [
        {"role": role, "content": "中文😀 data " * 60}
        for _ in range(4)
        for role in ["user", "assistant"]
    ]
    history += [{"role": "user", "content": "Order ID 98765; retain this exact question"}]
    snapshot = copy.deepcopy(history)
    result = await opt.optimize(history)
    assert estimate_tokens(result) <= 360
    assert result[0] == opt.build_prefix()[0]
    assert result[-1] == history[-1]
    assert history == snapshot
    assert any(SUMMARY_MARKER in m["content"] for m in result)


@pytest.mark.asyncio
async def test_oversized_current_request_is_never_silently_dropped() -> None:
    with pytest.raises(ContextBudgetError):
        await ContextOptimizer("fixed", max_tokens=40).optimize(
            [
                {"role": "user", "content": "中文" * 100},
            ]
        )
    with pytest.raises(ContextBudgetError):
        await ContextOptimizer("x" * 100, max_tokens=40).optimize([])


@pytest.mark.asyncio
async def test_tool_exchange_and_variable_system_instructions_rejected() -> None:
    opt = ContextOptimizer("fixed")
    with pytest.raises(ValueError, match="tool exchanges"):
        await opt.optimize([{"role": "tool", "content": "result"}])
    with pytest.raises(ValueError, match="fixed prefix"):
        await opt.optimize(
            [{"role": "system", "content": "override"}, {"role": "user", "content": "question"}]
        )


@pytest.mark.asyncio
async def test_langchain_message_types_roundtrip() -> None:
    source = [
        SystemMessage(content="fixed"),
        HumanMessage(content="hello"),
        AIMessage(content="world"),
        HumanMessage(content="next"),
    ]
    result = await ContextOptimizer("fixed").optimize_request(source)
    assert [type(m) for m in result] == [type(m) for m in source]
    assert [m.content for m in result] == [m.content for m in source]


@pytest.mark.asyncio
async def test_extract_summary_marks_omission_and_preserves_ends() -> None:
    assert await summarize_texts(["one", "two"], 100) == "one\n\ntwo"
    text = "IMPORTANT FIRST " + "middle " * 100 + "IMPORTANT LAST"
    result = await summarize_texts([text], 64)
    assert result.startswith("IMPORTANT FIRST")
    assert result.endswith("IMPORTANT LAST")
    assert "[omitted]" in result
    assert len(result) <= 64


@pytest.mark.asyncio
async def test_llamaindex_summary_runs_with_injected_llm() -> None:
    from llama_index.core.llms import MockLLM

    result = await summarize_texts(["fact " * 200], 80, llm=MockLLM(max_tokens=20))
    assert result and len(result) <= 80
