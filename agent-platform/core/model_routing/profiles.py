"""模型目錄只保存能力與環境變數名稱，不保存 API 金鑰。"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TaskType = Literal["general", "coding", "reasoning", "writing", "knowledge"]
Preference = Literal["balanced", "quality", "economy", "latency"]
Provider = Literal["demo", "openai-compatible", "anthropic", "google", "dashscope"]

ADAPTERS = {
    "openai-compatible": "langchain_openai",
    "anthropic": "langchain_anthropic",
    "google": "langchain_google_genai",
    "dashscope": "langchain_community",
}


class ModelProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
    label: str = Field(min_length=1, max_length=100)
    provider: Provider
    model: str = Field(min_length=1, max_length=200)
    model_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    base_url: str | None = None
    base_url_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    strengths: dict[TaskType, int] = Field(default_factory=lambda: {"general": 5})
    context_window: int = Field(default=8192, ge=512, le=2_000_000)
    max_output_tokens: int = Field(default=1024, ge=1)
    tool_calling: bool = True
    cost_tier: int = Field(default=2, ge=1, le=3)
    latency_tier: int = Field(default=2, ge=1, le=3)
    tenant_ids: tuple[str, ...] = ()
    enabled: bool = True

    @field_validator("id")
    @classmethod
    def reserved_id(cls, value: str) -> str:
        if value == "auto":
            raise ValueError("auto is reserved for automatic routing")
        return value

    @field_validator("strengths")
    @classmethod
    def strength_range(cls, values: dict[TaskType, int]) -> dict[TaskType, int]:
        if not values or any(value < 0 or value > 10 for value in values.values()):
            raise ValueError("Task strengths must be declared on a 0..10 scale")
        return values

    @model_validator(mode="after")
    def valid_context(self) -> ModelProfile:
        if self.max_output_tokens + 256 >= self.context_window:
            raise ValueError("Context window must leave room for input and protocol overhead")
        return self

    def model_name(self) -> str:
        return os.getenv(self.model_env, "") if self.model_env else self.model

    def endpoint(self) -> str | None:
        return os.getenv(self.base_url_env) or self.base_url if self.base_url_env else self.base_url

    def public(self) -> dict[str, object]:
        # 目錄回應不包含端點、租戶名單、金鑰或金鑰環境變數名稱。
        return {
            "id": self.id,
            "label": self.label,
            "provider": self.provider,
            "model": self.model_name(),
            "strengths": dict(self.strengths),
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "tool_calling": self.tool_calling,
            "cost_tier": self.cost_tier,
            "latency_tier": self.latency_tier,
        }


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    models: list[ModelProfile] = Field(min_length=1, max_length=64)


class ModelCatalog:
    def __init__(self, profiles: list[ModelProfile]) -> None:
        if not profiles or len({p.id for p in profiles}) != len(profiles):
            raise ValueError("Model IDs must be unique and the catalog cannot be empty")
        self.profiles = {profile.id: profile for profile in profiles}

    @classmethod
    def demo(cls) -> ModelCatalog:
        # 分數是示範用宣告，不代表真實供應商的實測能力。
        specifications = [
            ("demo-fast", "快速通用", {"general": 8, "writing": 7}, 1, 1, 8192),
            ("demo-coder", "程式專長", {"coding": 10, "general": 5}, 2, 2, 16384),
            ("demo-reasoner", "推理專長", {"reasoning": 10, "general": 5}, 3, 3, 32768),
            ("demo-writer", "寫作與知識", {"writing": 10, "knowledge": 10}, 2, 2, 16384),
        ]
        return cls(
            [
                ModelProfile(
                    id=mid,
                    label=label,
                    provider="demo",
                    model=mid,
                    strengths=strengths,
                    cost_tier=cost,
                    latency_tier=latency,
                    context_window=context,
                )
                for mid, label, strengths, cost, latency, context in specifications
            ]
        )

    @classmethod
    def from_environment(cls) -> ModelCatalog:
        if os.getenv("AGENT_PLATFORM_DEMO") == "1":
            return cls.demo()
        filename = os.getenv("PLATFORM_MODELS_FILE")
        if filename:
            try:
                raw = json.loads(Path(filename).read_text(encoding="utf-8"))
                return cls(ModelSettings.model_validate(raw).models)
            except (OSError, ValueError) as exc:
                raise RuntimeError(
                    "Invalid PLATFORM_MODELS_FILE; check model profile settings"
                ) from exc
        # 保留原有單一模型設定，未提供金鑰時仍可啟動路由預覽介面。
        tongyi = not os.getenv("LLM_API_KEY") and bool(os.getenv("DASHSCOPE_API_KEY"))
        return cls(
            [
                ModelProfile(
                    id="default-model",
                    label="環境預設模型",
                    provider="dashscope" if tongyi else "openai-compatible",
                    model=os.getenv("LLM_MODEL")
                    or ("qwen-turbo" if tongyi else "configured-model"),
                    model_env=None if tongyi else "LLM_MODEL",
                    api_key_env="DASHSCOPE_API_KEY" if tongyi else "LLM_API_KEY",
                    base_url_env=None if tongyi else "LLM_BASE_URL",
                    strengths={
                        task: 6
                        for task in ("general", "coding", "reasoning", "writing", "knowledge")
                    },
                )
            ]
        )

    def visible(self, tenant: str, allowed_ids: list[str] | None = None) -> list[ModelProfile]:
        return [
            profile
            for profile in self.profiles.values()
            if (not profile.tenant_ids or tenant in profile.tenant_ids)
            and (allowed_ids is None or profile.id in allowed_ids)
        ]

    @staticmethod
    def availability(profile: ModelProfile) -> tuple[bool, str]:
        if not profile.enabled:
            return False, "disabled"
        if not profile.model_name().strip():
            return False, "model_not_configured"
        if profile.provider == "demo":
            return True, "offline_demo"
        if profile.api_key_env and not os.getenv(profile.api_key_env):
            return False, "credentials_not_configured"
        if not profile.api_key_env and not profile.endpoint():
            return False, "endpoint_not_configured"
        if importlib.util.find_spec(ADAPTERS[profile.provider]) is None:
            return False, "adapter_not_installed"
        return True, "configured"

    def public(self, tenant: str, allowed_ids: list[str] | None = None) -> list[dict[str, object]]:
        result = []
        for profile in self.visible(tenant, allowed_ids):
            ready, status = self.availability(profile)
            result.append({**profile.public(), "available": ready, "status": status})
        return result
