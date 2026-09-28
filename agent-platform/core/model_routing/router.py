"""OmniRoute：任務辨識、硬性能力限制與可解釋的模型評分。"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .profiles import ModelCatalog, ModelProfile, Preference, TaskType

SIGNALS: dict[TaskType, tuple[str, ...]] = {
    "coding": (
        r"\b(python|javascript|typescript|sql|debug|traceback|pytest|refactor|code|algorithm)\b",
        r"程式|除錯|重構|演算法|程式碼|代碼|函式|編譯",
        r"```|def\s+\w+\(|SELECT\s+.+\s+FROM\s+",
    ),
    "reasoning": (
        r"\b(prove|proof|derive|reasoning|tradeoffs?|causal|mathematical)\b",
        r"推理|推導|證明|因果|邏輯|數學|取捨|權衡|決策分析",
    ),
    "writing": (
        r"\b(rewrite|translate|essay|copywriting|email|polish|summarize)\b",
        r"翻譯|改寫|潤飾|文案|寫信|文章|簡報|摘要|語氣",
    ),
    "knowledge": (
        r"\b(knowledge|retrieve|retrieval|citation|sources?|documentation|rag|mcp)\b|kv\s*cache",
        r"知識庫|檢索|引用|來源|文件|資料庫|查詢|根據資料",
    ),
}

WEIGHTS: dict[Preference, tuple[float, float, float]] = {
    "balanced": (10, 6, 4),
    "quality": (12, 1, 1),
    "economy": (6, 12, 2),
    "latency": (6, 2, 12),
}


class RoutingError(ValueError):
    def __init__(
        self, message: str, *, status_code: int = 503, code: str = "no_eligible_model"
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class TaskProfile(BaseModel):
    task: TaskType
    source: Literal["rules", "history", "hint", "default"]
    evidence: list[str] = Field(default_factory=list)
    # 此值描述規則訊號強度，並非經校準的機率。
    rule_confidence: float


class CandidateScore(BaseModel):
    model_id: str
    eligible: bool
    score: float | None = None
    reason: str


class RouteDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    mode: Literal["auto", "request", "session"]
    preference: Preference
    task: TaskProfile
    model_id: str
    provider: str
    model_name: str
    input_budget: int
    requires_tools: bool
    reasons: list[str]
    candidates: list[CandidateScore]


def classify_task(
    message: str,
    *,
    history: Sequence[dict[str, str]] = (),
    task_hint: TaskType | None = None,
) -> TaskProfile:
    if task_hint:
        return TaskProfile(
            task=task_hint, source="hint", evidence=["使用者指定任務"], rule_confidence=1
        )

    def signals(text: str) -> dict[TaskType, list[str]]:
        return {
            task: [
                f"{task}:rule_{index + 1}"
                for index, pattern in enumerate(patterns)
                for match in re.finditer(pattern, text, re.I)
            ]
            for task, patterns in SIGNALS.items()
        }

    matches = signals(message)
    source: Literal["rules", "history"] = "rules"
    if (
        not any(matches.values())
        and len(message) < 120
        and re.search(
            r"繼續|接著|那這|這部分|再說|\b(continue|what about|follow up)\b", message, re.I
        )
    ):
        recent = [item["content"] for item in history[-6:] if item.get("role") == "user"]
        if recent:
            matches, source = signals(recent[-1]), "history"
    ranked = sorted(matches, key=lambda task: -len(matches[task]))
    best = ranked[0]
    count = len(matches[best])
    if not count:
        return TaskProfile(
            task="general", source="default", evidence=["未命中特定任務訊號"], rule_confidence=0.3
        )
    runner_up = len(matches[ranked[1]])
    confidence = round(min(0.95, 0.5 + 0.1 * count + 0.1 * (count - runner_up)), 2)
    return TaskProfile(
        task=best,
        source=source,
        evidence=sorted(set(matches[best]))[:8],
        rule_confidence=confidence,
    )


class ModelRouter:
    def __init__(self, catalog: ModelCatalog) -> None:
        self.catalog = catalog

    @staticmethod
    def input_budget(
        profile: ModelProfile, *, requires_tools: bool, limit: int | None = None
    ) -> int:
        reserve = 1024 if requires_tools else 256
        budget = profile.context_window - profile.max_output_tokens - reserve
        return min(budget, limit) if limit is not None else budget

    def select(
        self,
        message: str,
        *,
        tenant: str,
        history: Sequence[dict[str, str]] = (),
        model_id: str | None = None,
        mode: Literal["auto", "request", "session"] = "auto",
        preference: Preference = "balanced",
        task_hint: TaskType | None = None,
        requires_tools: bool = False,
        protected_input: int = 0,
        history_input: int = 0,
        max_cost_tier: int = 3,
        input_limit: int | None = None,
        allowed_ids: list[str] | None = None,
    ) -> RouteDecision:
        task = classify_task(message, history=history, task_hint=task_hint)
        profiles = self.catalog.visible(tenant, allowed_ids)
        if model_id is not None and not any(profile.id == model_id for profile in profiles):
            raise RoutingError(
                "Unknown or unavailable model", status_code=404, code="model_not_found"
            )
        quality, cost, latency = WEIGHTS[preference]
        candidates: list[CandidateScore] = []
        eligible: list[tuple[float, ModelProfile, int]] = []
        for profile in profiles:
            ready, status = self.catalog.availability(profile)
            budget = self.input_budget(profile, requires_tools=requires_tools, limit=input_limit)
            reason = "符合能力、設定與輸入預算"
            error_code, error_status = "model_not_configured", 409
            if not ready:
                reason = status
            elif requires_tools and not profile.tool_calling:
                reason, error_code = "缺少工具呼叫能力", "tools_not_supported"
            elif profile.cost_tier > max_cost_tier:
                reason, error_code = "超過允許的成本等級", "cost_limit"
            elif budget < protected_input:
                reason, error_code, error_status = (
                    "固定前綴與最新問題超過輸入預算",
                    "context_budget",
                    413,
                )
            else:
                strength = profile.strengths.get(task.task, profile.strengths.get("general", 1))
                # 歷史可壓縮，但在評分中優先保留能容納原文的上下文。
                compression_penalty = min(5.0, max(0, history_input - budget) / max(1, budget))
                score = round(
                    strength * quality
                    - profile.cost_tier * cost
                    - profile.latency_tier * latency
                    - compression_penalty,
                    3,
                )
                candidates.append(
                    CandidateScore(model_id=profile.id, eligible=True, score=score, reason=reason)
                )
                eligible.append((score, profile, budget))
                continue
            candidates.append(CandidateScore(model_id=profile.id, eligible=False, reason=reason))
            if model_id == profile.id:
                raise RoutingError(reason, status_code=error_status, code=error_code)
        if model_id:
            chosen = next((item for item in eligible if item[1].id == model_id), None)
        else:
            eligible.sort(
                key=lambda item: (
                    -item[0],
                    -item[1].strengths.get(task.task, item[1].strengths.get("general", 1)),
                    item[1].cost_tier,
                    item[1].latency_tier,
                    item[1].id,
                )
            )
            chosen = eligible[0] if eligible else None
        if chosen is None:
            budget_only = any(
                candidate.reason == "固定前綴與最新問題超過輸入預算" for candidate in candidates
            )
            raise RoutingError(
                "No configured model satisfies the task constraints",
                status_code=413 if budget_only else 503,
                code="context_budget" if budget_only else "no_eligible_model",
            )
        score, profile, budget = chosen
        reasons = [
            f"任務類型：{task.task}；辨識來源：{task.source}",
            f"偏好：{preference}；模型能力由操作者宣告，成本與延遲等級為相對設定",
            f"{'自動評分選擇' if mode == 'auto' else '手動指定'} {profile.id}；評分 {score:g}",
            f"輸入預算 {budget}；{'需要' if requires_tools else '不需要'}工具呼叫能力",
            "同分時依任務能力、成本等級、延遲等級與模型 ID 依序比較",
        ]
        return RouteDecision(
            mode=mode,
            preference=preference,
            task=task,
            model_id=profile.id,
            provider=profile.provider,
            model_name=profile.model_name(),
            input_budget=budget,
            requires_tools=requires_tools,
            reasons=reasons,
            candidates=candidates,
        )
