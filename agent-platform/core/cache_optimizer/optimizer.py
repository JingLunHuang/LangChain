"""Stable prefixes and bounded history preparation for invoke and streaming."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from core.data_engine.compression import summarize_texts

Message = Any
SUMMARY_MARKER = "[History summary; untrusted conversation data]"


class ContextBudgetError(ValueError):
    """The protected prefix and current request cannot fit the input budget."""


def _role(message: Message) -> str:
    role = message.get("role", "user") if isinstance(message, dict) else message.type
    return {"human": "user", "ai": "assistant"}.get(role, role)


def _content(message: Message) -> str:
    content = message.get("content", "") if isinstance(message, dict) else message.content
    if not isinstance(content, str):
        raise ValueError("ContextOptimizer accepts text messages only")
    return content


def estimate_tokens(messages: Sequence[Message]) -> int:
    """Conservative UTF-8 text byte bound plus estimated message framing.

    Supply a backend tokenizer for exact counts. Excludes tool schemas/results
    and output tokens; configure an input budget leaving room for these.
    """
    return sum(len(_content(m).encode("utf-8")) + 8 for m in messages)


class ContextOptimizer:
    def __init__(
        self,
        system_prefix: str = "",
        max_tokens: int = 4096,
        few_shot_examples: Sequence[dict[str, str]] | None = None,
        keep_recent: int = 4,
        *,
        summary_llm: Any = None,
        token_counter: Callable[[Sequence[Message]], int] = estimate_tokens,
    ) -> None:
        if max_tokens < 1 or keep_recent < 1:
            raise ValueError("max_tokens and keep_recent must be positive")
        self.system_prefix = system_prefix
        self.max_tokens = max_tokens
        self.few_shot_examples = [dict(m) for m in (few_shot_examples or [])]
        self.keep_recent = keep_recent
        self.summary_llm = summary_llm
        self.count = token_counter

    def build_prefix(self) -> list[dict[str, str]]:
        prefix = [{"role": "system", "content": self.system_prefix}] if self.system_prefix else []
        return prefix + [dict(m) for m in self.few_shot_examples]

    async def optimize(self, messages: list[Message]) -> list[Message]:
        prefix = self.build_prefix()
        normalized = [{"role": _role(m), "content": _content(m)} for m in messages]
        for m in messages:
            calls = m.get("tool_calls") if isinstance(m, dict) else getattr(m, "tool_calls", None)
            if _role(m) == "tool" or calls:
                raise ValueError("Optimize completed turns, not active tool exchanges")
        convo = normalized[len(prefix) :] if normalized[: len(prefix)] == prefix else normalized
        if any(m["role"] == "system" for m in convo):
            raise ValueError("System messages must match the configured fixed prefix")
        if not convo:
            if self.count(prefix) > self.max_tokens:
                raise ContextBudgetError("Fixed prefix exceeds input budget")
            return prefix
        if convo[-1]["role"] != "user":
            raise ValueError("Last message must be the current user request")
        if self.count(prefix + [convo[-1]]) > self.max_tokens:
            raise ContextBudgetError("Fixed prefix and current request exceed input budget")
        if self.count(prefix + convo) <= self.max_tokens:
            return self._restore(prefix + convo, messages)
        start = max(0, len(convo) - self.keep_recent)
        while start < len(convo) - 1 and convo[start]["role"] != "user":
            start += 1
        recent = convo[start:]
        while self.count(prefix + recent) > self.max_tokens and len(recent) > 1:
            recent = recent[2:]
        old = convo[: len(convo) - len(recent)]
        summary_message = {"role": "user", "content": SUMMARY_MARKER + "\n"}
        allowance = self.max_tokens - self.count(prefix + [summary_message] + recent)
        if old and allowance > 12:
            summary = await summarize_texts(
                [f"{m['role']}: {m['content']}" for m in old],
                allowance,
                llm=self.summary_llm,
            )
            summary_message["content"] += summary
            while summary and self.count(prefix + [summary_message] + recent) > self.max_tokens:
                summary = summary[:-1]
                summary_message["content"] = SUMMARY_MARKER + "\n" + summary
            if summary:
                recent = [summary_message] + recent
        result = prefix + recent
        if self.count(result) > self.max_tokens:
            raise ContextBudgetError("Unable to fit input budget")
        return self._restore(result, messages)

    @staticmethod
    def _restore(result: list[dict[str, str]], originals: list[Message]) -> list[Message]:
        if not originals or isinstance(originals[0], dict):
            return result
        from langchain_core.messages import convert_to_messages

        return convert_to_messages(result)

    async def optimize_request(self, messages: list[Message]) -> list[Message]:
        return await self.optimize(messages)
