"""OmniRoute 模型路由層測試：任務辨識、硬性限制、偏好權重與可解釋決策。"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.model_routing.profiles import ModelCatalog, ModelProfile, Provider, TaskType
from core.model_routing.router import ModelRouter, RoutingError, classify_task

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_MODELS = PROJECT_ROOT / "models.example.json"


def make_profile(
    model_id: str,
    *,
    strengths: dict[TaskType, int] | None = None,
    cost_tier: int = 1,
    latency_tier: int = 1,
    tool_calling: bool = True,
    provider: Provider = "demo",
    enabled: bool = True,
    api_key_env: str | None = None,
    context_window: int = 8192,
    max_output_tokens: int = 1024,
) -> ModelProfile:
    return ModelProfile(
        id=model_id,
        label=model_id,
        provider=provider,
        model=model_id,
        strengths=strengths or {"general": 5},
        cost_tier=cost_tier,
        latency_tier=latency_tier,
        tool_calling=tool_calling,
        enabled=enabled,
        api_key_env=api_key_env,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
    )


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Refactor this python function and fix the traceback", "coding"),
        ("幫我除錯這段程式並重構函式", "coding"),
        ("Prove the theorem and derive the mathematical proof", "reasoning"),
        ("請證明這個數學定理的因果關係", "reasoning"),
        ("Rewrite and polish this email copywriting", "writing"),
        ("請幫我翻譯並潤飾這篇文章", "writing"),
        ("Retrieve the documentation with citation sources", "knowledge"),
        ("請從知識庫檢索文件並引用來源", "knowledge"),
        ("你好，今天過得怎麼樣", "general"),
        ("Hello, how are you today?", "general"),
    ],
)
def test_classify_task_rules(message: str, expected: TaskType) -> None:
    task = classify_task(message)
    assert task.task == expected
    if expected == "general":
        assert task.source == "default"
        assert task.rule_confidence == 0.3
    else:
        assert task.source == "rules"
        assert task.evidence
        assert 0.5 <= task.rule_confidence <= 0.95


def test_classify_task_hint_overrides_rules() -> None:
    task = classify_task("Refactor this python code", task_hint="writing")
    assert task.task == "writing"
    assert task.source == "hint"
    assert task.rule_confidence == 1


def test_short_followup_uses_recent_history() -> None:
    history = [
        {"role": "user", "content": "幫我除錯這段 python 程式"},
        {"role": "assistant", "content": "已修正"},
    ]
    task = classify_task("繼續", history=history)
    assert task.task == "coding"
    assert task.source == "history"


def test_short_followup_without_history_defaults_to_general() -> None:
    task = classify_task("繼續")
    assert task.task == "general"
    assert task.source == "default"


def test_long_followup_does_not_use_history() -> None:
    history = [{"role": "user", "content": "幫我除錯這段 python 程式"}]
    task = classify_task("繼續" + "好" * 130, history=history)
    assert task.task == "general"
    assert task.source == "default"


def test_from_environment_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_DEMO", "1")
    catalog = ModelCatalog.from_environment()
    assert set(catalog.profiles) == {"demo-fast", "demo-coder", "demo-reasoner", "demo-writer"}
    for profile in catalog.profiles.values():
        ready, status = ModelCatalog.availability(profile)
        assert ready
        assert status == "offline_demo"


def test_from_environment_models_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_PLATFORM_DEMO", raising=False)
    monkeypatch.setenv("PLATFORM_MODELS_FILE", str(EXAMPLE_MODELS))
    for name in ("FAST_API_KEY", "CODE_API_KEY", "REASON_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for name in ("FAST_MODEL", "CODE_MODEL", "REASON_MODEL", "CLAUDE_MODEL", "GEMINI_MODEL"):
        monkeypatch.setenv(name, "configured-model")
    catalog = ModelCatalog.from_environment()
    assert set(catalog.profiles) == {
        "fast-chat",
        "code-specialist",
        "deep-reasoning",
        "claude-native",
        "gemini-native",
    }
    statuses = {entry["id"]: entry["status"] for entry in catalog.public("tenant-a")}
    assert statuses["claude-native"] == "disabled"
    assert statuses["gemini-native"] == "disabled"
    assert statuses["fast-chat"] == "credentials_not_configured"


def test_from_environment_invalid_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AGENT_PLATFORM_DEMO", raising=False)
    broken = tmp_path / "models.json"
    broken.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("PLATFORM_MODELS_FILE", str(broken))
    with pytest.raises(RuntimeError, match="PLATFORM_MODELS_FILE"):
        ModelCatalog.from_environment()


def test_hard_constraints_exclude_candidates() -> None:
    catalog = ModelCatalog(
        [
            make_profile("eligible"),
            make_profile("off", enabled=False),
            make_profile("no-tools", tool_calling=False),
            make_profile("pricey", cost_tier=3),
        ]
    )
    decision = ModelRouter(catalog).select(
        "一般問題", tenant="t", requires_tools=True, max_cost_tier=1, task_hint="general"
    )
    assert decision.model_id == "eligible"
    excluded = {c.model_id: c for c in decision.candidates if not c.eligible}
    assert excluded["off"].reason == "disabled"
    assert excluded["no-tools"].reason == "缺少工具呼叫能力"
    assert excluded["pricey"].reason == "超過允許的成本等級"
    assert all(c.score is None for c in excluded.values())


def test_unavailable_model_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_CREDENTIALS", raising=False)
    catalog = ModelCatalog(
        [
            make_profile("ready"),
            make_profile(
                "no-cred",
                provider="openai-compatible",
                api_key_env="MISSING_CREDENTIALS",
            ),
        ]
    )
    decision = ModelRouter(catalog).select("一般問題", tenant="t", task_hint="general")
    assert decision.model_id == "ready"
    excluded = {c.model_id: c for c in decision.candidates if not c.eligible}
    assert excluded["no-cred"].reason == "credentials_not_configured"


def test_manual_model_without_tool_support_raises() -> None:
    catalog = ModelCatalog([make_profile("no-tools", tool_calling=False)])
    with pytest.raises(RoutingError) as excinfo:
        ModelRouter(catalog).select(
            "呼叫工具", tenant="t", model_id="no-tools", requires_tools=True
        )
    assert excinfo.value.code == "tools_not_supported"
    assert excinfo.value.status_code == 409


def test_manual_model_over_cost_limit_raises() -> None:
    catalog = ModelCatalog([make_profile("pricey", cost_tier=3)])
    with pytest.raises(RoutingError) as excinfo:
        ModelRouter(catalog).select("省錢", tenant="t", model_id="pricey", max_cost_tier=1)
    assert excinfo.value.code == "cost_limit"
    assert excinfo.value.status_code == 409


def test_manual_disabled_model_raises() -> None:
    catalog = ModelCatalog([make_profile("off", enabled=False)])
    with pytest.raises(RoutingError) as excinfo:
        ModelRouter(catalog).select("任意", tenant="t", model_id="off")
    assert excinfo.value.code == "model_not_configured"
    assert excinfo.value.status_code == 409


def test_unknown_model_id_raises_not_found() -> None:
    router = ModelRouter(ModelCatalog.demo())
    with pytest.raises(RoutingError) as excinfo:
        router.select("任意問題", tenant="t", model_id="no-such-model")
    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "model_not_found"


def test_unknown_model_id_not_visible_for_tenant() -> None:
    restricted = ModelProfile(
        id="internal",
        label="internal",
        provider="demo",
        model="internal",
        tenant_ids=("tenant-a",),
    )
    router = ModelRouter(ModelCatalog([make_profile("public"), restricted]))
    with pytest.raises(RoutingError) as excinfo:
        router.select("任意問題", tenant="tenant-b", model_id="internal")
    assert excinfo.value.code == "model_not_found"


def test_no_eligible_model_raises() -> None:
    catalog = ModelCatalog([make_profile("off", enabled=False)])
    with pytest.raises(RoutingError) as excinfo:
        ModelRouter(catalog).select("任意", tenant="t")
    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "no_eligible_model"


def test_context_budget_exceeded_raises_413() -> None:
    catalog = ModelCatalog([make_profile("small", context_window=8192, max_output_tokens=1024)])
    with pytest.raises(RoutingError) as excinfo:
        ModelRouter(catalog).select("任意", tenant="t", protected_input=100_000)
    assert excinfo.value.status_code == 413
    assert excinfo.value.code == "context_budget"


def test_preference_changes_selected_model() -> None:
    catalog = ModelCatalog(
        [
            make_profile(
                "strong-pricey", strengths={"coding": 5, "general": 2}, cost_tier=3, latency_tier=3
            ),
            make_profile(
                "weak-cheap", strengths={"coding": 3, "general": 2}, cost_tier=1, latency_tier=1
            ),
        ]
    )
    router = ModelRouter(catalog)
    quality = router.select("寫程式", tenant="t", task_hint="coding", preference="quality")
    economy = router.select("寫程式", tenant="t", task_hint="coding", preference="economy")
    assert quality.model_id == "strong-pricey"
    assert economy.model_id == "weak-cheap"
    scores = {c.model_id: c.score for c in quality.candidates}
    assert scores["strong-pricey"] > scores["weak-cheap"]


def test_demo_catalog_routes_tasks_to_specialists() -> None:
    router = ModelRouter(ModelCatalog.demo())
    coding = router.select("Refactor this python code", tenant="t")
    assert coding.model_id == "demo-coder"
    reasoning = router.select("Prove and derive the mathematical proof", tenant="t")
    assert reasoning.model_id == "demo-reasoner"


def test_decision_explainable_fields() -> None:
    catalog = ModelCatalog([make_profile("ready"), make_profile("off", enabled=False)])
    decision = ModelRouter(catalog).select(
        "Refactor this python code", tenant="t", preference="balanced"
    )
    assert decision.decision_id
    assert decision.mode == "auto"
    assert decision.preference == "balanced"
    assert decision.task.task == "coding"
    assert decision.task.source == "rules"
    assert decision.task.evidence
    assert decision.model_id == "ready"
    assert decision.provider == "demo"
    assert decision.model_name == "ready"
    assert decision.input_budget > 0
    assert len(decision.reasons) >= 3
    assert len(decision.candidates) == 2
    eligible = next(c for c in decision.candidates if c.eligible)
    excluded = next(c for c in decision.candidates if not c.eligible)
    assert eligible.score is not None
    assert eligible.reason
    assert excluded.score is None
    assert excluded.reason == "disabled"


def test_manual_mode_decision() -> None:
    router = ModelRouter(ModelCatalog.demo())
    decision = router.select("任意問題", tenant="t", model_id="demo-fast", mode="request")
    assert decision.mode == "request"
    assert decision.model_id == "demo-fast"
    assert any("手動指定" in reason for reason in decision.reasons)


def test_input_budget_reserves() -> None:
    profile = make_profile("p", context_window=8192, max_output_tokens=1024)
    assert ModelRouter.input_budget(profile, requires_tools=False) == 8192 - 1024 - 256
    assert ModelRouter.input_budget(profile, requires_tools=True) == 8192 - 1024 - 1024
    assert ModelRouter.input_budget(profile, requires_tools=False, limit=100) == 100


def test_allowed_ids_limit_visible_models() -> None:
    catalog = ModelCatalog([make_profile("a"), make_profile("b")])
    decision = ModelRouter(catalog).select(
        "任意問題", tenant="t", allowed_ids=["b"], task_hint="general"
    )
    assert decision.model_id == "b"
    assert {c.model_id for c in decision.candidates} == {"b"}
