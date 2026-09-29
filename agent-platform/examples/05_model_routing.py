"""課程範例 05：OmniRoute 任務分類與模型策略路由。

展示內容：
1. 載入 ModelCatalog（demo 模式為內建示範目錄，否則讀 PLATFORM_MODELS_FILE /
   models.example.json），列出對租戶可見的模型與設定狀態；
2. 五類任務（general/coding/reasoning/writing/knowledge）中英文混合示例的路由預覽，
   包含任務辨識、候選評分與排除原因；
3. 同一任務在 quality 與 economy 偏好下的選模差異；
4. session 固定模型後再恢復自動路由；
5. demo 模式下的真實執行（invoke）並印出 route 決策資訊。

執行方式（無需任何 API 金鑰）：
    AGENT_PLATFORM_DEMO=1 uv run python -m examples.05_model_routing
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("AGENT_PLATFORM_DEMO", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.model_routing.profiles import ModelCatalog
from core.model_routing.router import ModelRouter, RouteDecision
from core.orchestrator.runtime import AgentRuntime, Session

TENANT = "demo-tenant"

TASK_EXAMPLES: list[tuple[str, str]] = [
    ("general", "你好，please briefly introduce yourself 然後跟我聊聊今天的天氣"),
    ("coding", "幫我用 python 寫一個 def quicksort(arr) 函式並 debug 這段程式碼"),
    ("reasoning", "Prove the tradeoff：請推導並分析這個決策的因果關係與權衡"),
    ("writing", "請幫我 translate 這封 email 並 polish 語氣，改寫成正式文案"),
    ("knowledge", "根據知識庫檢索文件並回答，cite the sources 引用來源"),
]


def step_catalog(catalog: ModelCatalog) -> None:
    print("=" * 70)
    print("步驟 1：載入模型目錄並列出可見模型")
    print("=" * 70)
    if os.getenv("AGENT_PLATFORM_DEMO") == "1":
        source = "demo 內建示範目錄（AGENT_PLATFORM_DEMO=1）"
    else:
        source = os.getenv("PLATFORM_MODELS_FILE", "models.example.json / 環境預設")
    print(f"目錄來源：{source}")
    for item in catalog.public(TENANT):
        strengths = ", ".join(f"{task}={score}" for task, score in item["strengths"].items())
        print(
            f"  - {item['id']}（{item['label']}）provider={item['provider']} "
            f"cost={item['cost_tier']} latency={item['latency_tier']} "
            f"ctx={item['context_window']}"
        )
        print(f"      能力：{strengths}")
        print(f"      可用：{item['available']}（{item['status']}）")


def print_decision(decision: RouteDecision) -> None:
    task = decision.task
    print(f"  任務辨識：{task.task}（來源={task.source}，規則信心={task.rule_confidence}）")
    if task.evidence:
        print(f"  命中訊號：{', '.join(task.evidence)}")
    print(
        f"  選中模型：{decision.model_id}（provider={decision.provider}，"
        f"模式={decision.mode}，偏好={decision.preference}）"
    )
    print(f"  輸入預算：{decision.input_budget} tokens")
    for candidate in decision.candidates:
        if candidate.eligible:
            print(f"      [候選] {candidate.model_id}：評分 {candidate.score}")
        else:
            print(f"      [排除] {candidate.model_id}：{candidate.reason}")


def step_task_routing(router: ModelRouter) -> None:
    print()
    print("=" * 70)
    print("步驟 2：五類任務的路由預覽（中英文混合示例）")
    print("=" * 70)
    for expected, message in TASK_EXAMPLES:
        print(f"\n--- 示例（預期 {expected}）：{message}")
        decision = router.select(message, tenant=TENANT)
        print_decision(decision)
    print("\n--- 排除原因示範：同一推理任務限制成本等級 max_cost_tier=1")
    decision = router.select(TASK_EXAMPLES[2][1], tenant=TENANT, max_cost_tier=1)
    print_decision(decision)


def step_preference(router: ModelRouter) -> None:
    print()
    print("=" * 70)
    print("步驟 3：同一任務在 quality 與 economy 偏好下的選模差異")
    print("=" * 70)
    message = TASK_EXAMPLES[2][1]
    print(f"任務：{message}")
    for preference in ("quality", "economy"):
        decision = router.select(message, tenant=TENANT, preference=preference)
        chosen = next(item for item in decision.candidates if item.model_id == decision.model_id)
        print(f"  preference={preference:<8} -> {decision.model_id}（評分 {chosen.score}）")


async def step_session(runtime: AgentRuntime) -> tuple[str, Session]:
    print()
    print("=" * 70)
    print("步驟 4：session 固定模型 -> 恢復自動路由")
    print("=" * 70)
    sid, state = runtime.session(TENANT, "chat", None)
    message = "幫我用 python 重構這段程式碼"
    decision = runtime.plan(TENANT, "chat", state, message)
    print(f"初始（自動路由）：mode={decision.mode}，選中 {decision.model_id}")

    switched = await runtime.switch_model(TENANT, "chat", state, "demo-fast")
    print(f"切換後 session 狀態：{switched}")
    decision = runtime.plan(TENANT, "chat", state, message)
    print(f"固定模型後：mode={decision.mode}，選中 {decision.model_id}（不論任務類型）")

    restored = await runtime.switch_model(TENANT, "chat", state, "auto")
    print(f"恢復後 session 狀態：{restored}")
    decision = runtime.plan(TENANT, "chat", state, message)
    print(f"恢復自動路由：mode={decision.mode}，選中 {decision.model_id}")
    return sid, state


async def step_invoke(runtime: AgentRuntime, sid: str, state: Session) -> None:
    print()
    print("=" * 70)
    print("步驟 5：demo 模式真實執行一次 invoke（離線 Mock，不呼叫外部 API）")
    print("=" * 70)
    message = "用一句話說明什麼是 KV cache，並根據知識庫文件回答"
    result = await runtime.invoke_with_route(TENANT, "chat", sid, state, message)
    print(f"提問：{message}")
    print(f"回答：{result.output}")
    route = result.route
    print(
        f"route：decision_id={route.decision_id} model={route.model_id} "
        f"task={route.task.task} mode={route.mode} preference={route.preference}"
    )
    print("決策理由：")
    for reason in route.reasons:
        print(f"  - {reason}")


async def main() -> None:
    catalog = ModelCatalog.from_environment()
    router = ModelRouter(catalog)
    runtime = AgentRuntime(catalog=catalog)

    step_catalog(catalog)
    step_task_routing(router)
    step_preference(router)
    sid, state = await step_session(runtime)
    await step_invoke(runtime, sid, state)

    print()
    print("範例執行完畢。")


if __name__ == "__main__":
    asyncio.run(main())
