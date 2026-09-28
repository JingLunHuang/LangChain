"""編排層：基於 RunnableWithMessageHistory 的多會話記憶管理。"""

from __future__ import annotations

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory

DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."


class ConversationManager:
    """按 session_id 隔離的非同步多輪對話管理器。"""

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        if llm is None:
            from core.orchestrator.agent import create_default_llm

            llm = create_default_llm()
        self._store: dict[str, InMemoryChatMessageHistory] = {}
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{input}"),
            ]
        )
        self._conversation = RunnableWithMessageHistory(
            prompt | llm,
            self.get_session_history,
            input_messages_key="input",
            history_messages_key="history",
        )

    def get_session_history(self, session_id: str) -> InMemoryChatMessageHistory:
        if session_id not in self._store:
            self._store[session_id] = InMemoryChatMessageHistory()
        return self._store[session_id]

    async def achat(self, message: str, session_id: str = "default") -> str:
        """向指定會話發送一條訊息並回傳模型回覆文字。"""
        config = {"configurable": {"session_id": session_id}}
        output = await self._conversation.ainvoke({"input": message}, config=config)
        content = getattr(output, "content", output)
        return content if isinstance(content, str) else str(content)

    def clear(self, session_id: str) -> None:
        """清空指定會話的歷史記錄。"""
        self._store.pop(session_id, None)

    def session_ids(self) -> list[str]:
        return list(self._store.keys())
