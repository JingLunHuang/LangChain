"""課程範例 03：ConversationManager 管理不同 session 的對話記憶。

此教學管理器使用固定模型；租戶隔離、任務選模與歷史預算由 AgentRuntime 提供。
執行：uv run python -m examples.03_memory_conversation
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

    print("=== 會話 A：多輪記憶 ===")
    await chat_round(manager, "session-a", "你好，我叫小明，請記住我的名字。")
    await chat_round(manager, "session-a", "我剛纔告訴你我叫什麼名字？")

    print("=== 會話 B：獨立對話 ===")
    await chat_round(manager, "session-b", "你好！你知道我叫什麼名字嗎？")


if __name__ == "__main__":
    asyncio.run(main())
