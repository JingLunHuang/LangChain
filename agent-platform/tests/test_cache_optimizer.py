"""Tests for core.cache_optimizer: stable prefixes, passthrough, compression, budgets."""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from core.cache_optimizer.optimizer import (
    SUMMARY_MARKER,
    ContextBudgetError,
    ContextOptimizer,
    estimate_tokens,
)


def _dict_convo(contents: list[str]) -> list[dict[str, str]]:
    roles = ["user" if i % 2 == 0 else "assistant" for i in range(len(contents) - 1)]
    roles.append("user")
    return [{"role": role, "content": text} for role, text in zip(roles, contents, strict=True)]


def _wire(messages: list[dict[str, str]]) -> bytes:
    return json.dumps(messages, ensure_ascii=False, sort_keys=True).encode("utf-8")


class TestEstimation:
    def test_empty_sequence_is_zero(self) -> None:
        assert estimate_tokens([]) == 0

    def test_framing_overhead_per_message(self) -> None:
        assert estimate_tokens([{"role": "user", "content": ""}]) == 8

    def test_ascii_counts_bytes_plus_framing(self) -> None:
        assert estimate_tokens([{"role": "user", "content": "abc"}]) == 3 + 8

    def test_multibyte_counts_utf8_bytes_not_characters(self) -> None:
        assert estimate_tokens([{"role": "user", "content": "汉字"}]) == 6 + 8

    def test_conservative_lower_bound(self) -> None:
        contents = ["hello world", "汉字测试" * 20, "x" * 500]
        messages = [{"role": "user", "content": c} for c in contents]
        estimate = estimate_tokens(messages)
        assert estimate >= sum(len(c) for c in contents)
        assert estimate == sum(len(c.encode("utf-8")) + 8 for c in contents)

    def test_accepts_base_messages(self) -> None:
        messages = [HumanMessage(content="abc"), AIMessage(content="汉字")]
        assert estimate_tokens(messages) == (3 + 8) + (6 + 8)


class TestPrefixStability:
    def test_build_prefix_is_deterministic_bytes(self) -> None:
        optimizer = ContextOptimizer(
            system_prefix="You are OmniAgent.",
            few_shot_examples=[
                {"role": "user", "content": "q1"},
                {"role": "assistant", "content": "a1"},
            ],
        )
        first, second = optimizer.build_prefix(), optimizer.build_prefix()
        assert first == second
        assert _wire(first) == _wire(second)

    def test_prefix_includes_system_and_few_shots_in_order(self) -> None:
        optimizer = ContextOptimizer(
            system_prefix="SYS",
            few_shot_examples=[
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "a"},
            ],
        )
        assert optimizer.build_prefix() == [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
        ]

    def test_build_prefix_returns_independent_copies(self) -> None:
        few_shots = [{"role": "user", "content": "q"}]
        optimizer = ContextOptimizer(system_prefix="SYS", few_shot_examples=few_shots)
        few_shots[0]["content"] = "mutated"
        built = optimizer.build_prefix()
        built[0]["content"] = "mutated"
        assert optimizer.build_prefix() == [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "q"},
        ]

    def test_empty_prefix_builds_empty(self) -> None:
        assert ContextOptimizer().build_prefix() == []

    async def test_leading_messages_matching_prefix_are_deduplicated(self) -> None:
        optimizer = ContextOptimizer(system_prefix="SYS")
        messages = [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "hi"},
        ]
        result = await optimizer.optimize(messages)
        assert result == [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "hi"},
        ]

    async def test_repeated_optimize_yields_identical_bytes(self) -> None:
        optimizer = ContextOptimizer(system_prefix="SYS")
        messages = _dict_convo(["one", "two", "three"])
        first = await optimizer.optimize(messages)
        second = await optimizer.optimize(messages)
        assert _wire(first) == _wire(second)


class TestSystemMessagePlacement:
    async def test_scattered_system_message_is_rejected(self) -> None:
        optimizer = ContextOptimizer(system_prefix="SYS")
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "again"},
        ]
        with pytest.raises(ValueError, match="fixed prefix"):
            await optimizer.optimize(messages)

    async def test_mismatched_system_message_is_rejected(self) -> None:
        optimizer = ContextOptimizer(system_prefix="SYS")
        messages = [
            {"role": "system", "content": "OTHER"},
            {"role": "user", "content": "hi"},
        ]
        with pytest.raises(ValueError, match="fixed prefix"):
            await optimizer.optimize(messages)


class TestPassthrough:
    async def test_within_budget_is_byte_identical(self) -> None:
        optimizer = ContextOptimizer(system_prefix="SYS")
        contents = ["line one\nline two\n\n", "  spaced 汉字 content  ", "trailing\tTab"]
        messages = _dict_convo(contents)
        result = await optimizer.optimize(messages)
        assert result[0] == {"role": "system", "content": "SYS"}
        assert [m["content"] for m in result[1:]] == contents
        assert _wire(result[1:]) == _wire(messages)

    async def test_human_ai_role_aliases_normalized(self) -> None:
        optimizer = ContextOptimizer()
        messages = [
            {"role": "human", "content": "q"},
            {"role": "ai", "content": "a"},
            {"role": "user", "content": "q2"},
        ]
        result = await optimizer.optimize(messages)
        assert [m["role"] for m in result] == ["user", "assistant", "user"]

    async def test_empty_input_returns_prefix_only(self) -> None:
        optimizer = ContextOptimizer(system_prefix="SYS")
        assert await optimizer.optimize([]) == [{"role": "system", "content": "SYS"}]

    async def test_base_messages_restored_as_base_messages(self) -> None:
        optimizer = ContextOptimizer(system_prefix="SYS")
        messages: list[BaseMessage] = [
            HumanMessage(content="hello 汉字"),
            AIMessage(content="hi there"),
            HumanMessage(content="again"),
        ]
        result = await optimizer.optimize(messages)
        assert all(isinstance(m, BaseMessage) for m in result)
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[1], HumanMessage)
        assert isinstance(result[2], AIMessage)
        assert [m.content for m in result] == ["SYS", "hello 汉字", "hi there", "again"]

    async def test_optimize_request_delegates_to_optimize(self) -> None:
        optimizer = ContextOptimizer(system_prefix="SYS")
        messages = _dict_convo(["a", "b", "c"])
        assert await optimizer.optimize_request(messages) == await optimizer.optimize(messages)


class TestCompression:
    def _optimizer(self, max_tokens: int = 200, keep_recent: int = 3) -> ContextOptimizer:
        return ContextOptimizer(system_prefix="SYS", max_tokens=max_tokens, keep_recent=keep_recent)

    async def test_over_budget_compresses_old_history(self) -> None:
        optimizer = self._optimizer()
        messages = _dict_convo(["x" * 24] * 9)
        assert estimate_tokens(optimizer.build_prefix() + messages) > 200
        result = await optimizer.optimize(messages)
        assert estimate_tokens(result) <= 200
        assert result[0] == {"role": "system", "content": "SYS"}
        summary = result[1]
        assert summary["role"] == "user"
        assert summary["content"].startswith(SUMMARY_MARKER + "\n")
        assert "[omitted]" in summary["content"]
        assert result[-3:] == messages[-3:]

    async def test_fixed_prefix_never_compressed(self) -> None:
        optimizer = self._optimizer(max_tokens=120, keep_recent=1)
        messages = _dict_convo(["y" * 30] * 7)
        result = await optimizer.optimize(messages)
        assert result[0] == {"role": "system", "content": "SYS"}
        assert estimate_tokens(result) <= 120

    async def test_recent_boundary_starts_on_user_message(self) -> None:
        optimizer = self._optimizer(max_tokens=200, keep_recent=2)
        messages = _dict_convo(["x" * 24] * 9)
        result = await optimizer.optimize(messages)
        tail = [m for m in result if not m["content"].startswith(SUMMARY_MARKER)][1:]
        assert tail[0]["role"] == "user"

    async def test_no_summary_when_allowance_too_small(self) -> None:
        optimizer = self._optimizer(max_tokens=200, keep_recent=3)
        messages = _dict_convo(["z" * 40] * 9)
        result = await optimizer.optimize(messages)
        assert estimate_tokens(result) <= 200
        assert all(not m["content"].startswith(SUMMARY_MARKER) for m in result)
        assert result == optimizer.build_prefix() + messages[-3:]

    async def test_summary_trimmed_until_budget_with_multibyte_content(self) -> None:
        optimizer = ContextOptimizer(max_tokens=150, keep_recent=2)
        messages = _dict_convo(["汉" * 40, "汉" * 40, "汉" * 10])
        result = await optimizer.optimize(messages)
        assert estimate_tokens(result) <= 150
        assert result[-1]["content"] == "汉" * 10
        for m in result[:-1]:
            assert m["content"].startswith(SUMMARY_MARKER)

    async def test_compression_with_base_message_input(self) -> None:
        optimizer = self._optimizer()
        raw = _dict_convo(["x" * 24] * 9)
        messages: list[BaseMessage] = [
            HumanMessage(content=m["content"])
            if m["role"] == "user"
            else AIMessage(content=m["content"])
            for m in raw
        ]
        result = await optimizer.optimize(messages)
        assert all(isinstance(m, BaseMessage) for m in result)
        assert isinstance(result[0], SystemMessage)
        assert result[1].content.startswith(SUMMARY_MARKER)
        assert estimate_tokens(result) <= 200


class TestBudgetRejection:
    async def test_fixed_prefix_alone_exceeding_budget_raises(self) -> None:
        optimizer = ContextOptimizer(system_prefix="p" * 100, max_tokens=10)
        with pytest.raises(ContextBudgetError, match="Fixed prefix exceeds"):
            await optimizer.optimize([])

    async def test_prefix_plus_current_request_exceeding_budget_raises(self) -> None:
        optimizer = ContextOptimizer(system_prefix="SYS", max_tokens=30)
        with pytest.raises(ContextBudgetError, match="current request exceed"):
            await optimizer.optimize([{"role": "user", "content": "r" * 50}])

    def test_budget_error_is_a_value_error(self) -> None:
        assert issubclass(ContextBudgetError, ValueError)


class TestInputValidation:
    def test_constructor_rejects_non_positive_budget(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            ContextOptimizer(max_tokens=0)

    def test_constructor_rejects_non_positive_keep_recent(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            ContextOptimizer(keep_recent=0)

    async def test_last_message_must_be_user(self) -> None:
        optimizer = ContextOptimizer()
        messages = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
        ]
        with pytest.raises(ValueError, match="current user request"):
            await optimizer.optimize(messages)

    async def test_tool_role_message_rejected(self) -> None:
        optimizer = ContextOptimizer()
        messages = [
            {"role": "tool", "content": "result"},
            {"role": "user", "content": "q"},
        ]
        with pytest.raises(ValueError, match="tool exchanges"):
            await optimizer.optimize(messages)

    async def test_tool_calls_rejected_for_dicts_and_base_messages(self) -> None:
        optimizer = ContextOptimizer()
        dict_messages = [
            {"role": "assistant", "content": "", "tool_calls": [{"name": "t"}]},
            {"role": "user", "content": "q"},
        ]
        with pytest.raises(ValueError, match="tool exchanges"):
            await optimizer.optimize(dict_messages)
        lc_messages: list[BaseMessage] = [
            AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "1"}]),
            HumanMessage(content="q"),
        ]
        with pytest.raises(ValueError, match="tool exchanges"):
            await optimizer.optimize(lc_messages)

    async def test_non_text_content_rejected(self) -> None:
        optimizer = ContextOptimizer()
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "q"}]},
        ]
        with pytest.raises(ValueError, match="text messages only"):
            await optimizer.optimize(messages)  # type: ignore[arg-type]
