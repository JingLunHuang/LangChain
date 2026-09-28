"""離線操作模式專用的聊天與向量 adapter，與正式供應商及檢索實作分開。"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterator, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from llama_index.core.base.embeddings.base import BaseEmbedding

from core.data_engine.retrieval import tokenize


class DemoChatModel(BaseChatModel):
    profile_id: str = "demo-fast"
    tool_names: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "offline-demo"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> DemoChatModel:
        return self.model_copy(update={"tool_names": [getattr(t, "name", "") for t in tools]})

    def _answer(self, messages: list[BaseMessage]) -> AIMessage:
        last = messages[-1]
        if isinstance(last, ToolMessage):
            return AIMessage(
                content=f"[Offline demo / {self.profile_id}: retrieved excerpts]\n"
                + str(last.content)
            )
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
        return AIMessage(content=f"[Offline demo / {self.profile_id}] " + str(last.content))

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


class DemoEmbedding(BaseEmbedding):
    """Hashed lexical vectors for offline operation; no semantic quality claims."""

    model_name: str = "demo-lexical-hash-256"

    def _get_text_embedding(self, text: str) -> list[float]:
        vector = [0.0] * 256
        for token in tokenize(text):
            bucket = int.from_bytes(hashlib.sha256(token.encode()).digest()[:2], "big") % 256
            vector[bucket] += 1
        norm = math.sqrt(sum(value * value for value in vector)) or 1
        return [value / norm for value in vector]

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._get_text_embedding(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)
