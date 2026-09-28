"""離線展示任務選模、手動切換、保留對話與恢復自動選模。"""

from __future__ import annotations

import asyncio

from core.model_routing.profiles import ModelCatalog
from core.orchestrator.runtime import AgentRuntime, Session

CASES = [
    "你好，介紹一下這個平台。",
    "請用 Python 寫一個非同步函式並除錯。",
    "請逐步推導並證明這個數學命題。",
    "請把這封 email 改寫成正式的文章。",
    "根據知識庫文件檢索 KV cache，並引用來源。",
]


async def main() -> None:
    runtime = AgentRuntime(catalog=ModelCatalog.demo())
    print("OmniRoute / Offline task-to-model showcase")
    for message in CASES:
        decision = runtime.plan("portfolio", "chat", Session(), message)
        print(f"{decision.task.task:10} -> {decision.model_id:16} | {message}")
    sid, state = runtime.session("portfolio", "chat", "portfolio-session")
    first = await runtime.invoke_with_route("portfolio", "chat", sid, state, CASES[1])
    print("Automatic execution:", first.route.model_id, first.output)
    switched = await runtime.switch_model("portfolio", "chat", state, "demo-reasoner")
    print("Session switch:", switched)
    second = await runtime.invoke_with_route("portfolio", "chat", sid, state, "繼續說明。")
    print("Pinned execution:", second.route.model_id, second.route.mode)
    await runtime.switch_model("portfolio", "chat", state, None)
    final = await runtime.invoke_with_route("portfolio", "chat", sid, state, CASES[3])
    print("Automatic again:", final.route.model_id, final.route.mode)
    print("Retained history messages:", len(state.history))


if __name__ == "__main__":
    asyncio.run(main())
