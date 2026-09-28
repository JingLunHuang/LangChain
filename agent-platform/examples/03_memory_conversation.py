"""示例 03：多輪記憶對話


（ChatPromptTemplate + MessagesPlaceholder + RunnableWithMessageHistory
 手工拼裝 memory chain，session 歷史存放在全域 dict 中）

新架構改進點：
- 不再手工拼裝 RunnableWithMessageHistory，改由編排層
  core.orchestrator.memory.ConversationManager 統一管理會話歷史，
  由管理器保存並注入此教學範例的會話歷史；
- 演示多 session 隔離：同一 ConversationManager 實例按 session_id
  維護相互獨立的對話上下文；此管理器本身沒有租戶隔離或歷史截短。
- 平臺 API 使用 platform_api/api.py 與 AgentRuntime，另外提供
  租戶／Agent／會話隔離、上下文預算及串流。

介面約定：ConversationManager() 無需參數（LLM 由編排層注入），
非同步方法 achat(message: str, session_id: str = "default") -> str 回傳模型回覆。

執行方式（在 agent-platform 根目錄下）：
    python examples/03_memory_conversation.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.orchestrator.memory import ConversationManager


async def chat_round(manager: ConversationManager, session_id: str, message: str) -> None:
    reply = await manager.achat(message=message, session_id=session_id)
    print(f"[{session_id}] 用戶: {message}")
    print(f"[{session_id}] 助手: {reply}\n")


async def main() -> None:
    manager = ConversationManager()

    print("=== 會話 A：驗證多輪記憶 ===")
    await chat_round(manager, "session-a", "你好，我叫小明，請記住我的名字。")
    await chat_round(manager, "session-a", "我剛纔告訴你我叫什麼名字？")

    print("=== 會話 B：驗證 session 隔離 ===")
    await chat_round(manager, "session-b", "你好！你知道我叫什麼名字嗎？")


if __name__ == "__main__":
    asyncio.run(main())
