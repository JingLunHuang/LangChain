"""Deterministic offline demo model that exercises real LangChain tool dispatch."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


class DemoChatModel(BaseChatModel):
    tool_names: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "offline-demo"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> DemoChatModel:
        return self.model_copy(update={"tool_names": [getattr(t, "name", "") for t in tools]})

    def _answer(self, messages: list[BaseMessage]) -> AIMessage:
        last = messages[-1]
        if isinstance(last, ToolMessage):
            return AIMessage(content="[Offline demo: retrieved excerpts]\n" + str(last.content))
        if "hybrid_retrieve" in self.tool_names:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "hybrid_retrieve",
                        "args": {"query": str(last.content)},
                        "id": "demo-call",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="[Offline demo] " + str(last.content))

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._answer(messages))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        answer = self._answer(messages)
        if answer.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(content="", tool_calls=answer.tool_calls)
            )
        else:
            content = str(answer.content)
            for offset in range(0, len(content), 24):
                yield ChatGenerationChunk(
                    message=AIMessageChunk(content=content[offset : offset + 24])
                )
