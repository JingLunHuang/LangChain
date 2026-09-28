"""將平台模型設定轉換為供應商 adapter，路由策略不依賴 LangChain。"""

from __future__ import annotations

import os
from typing import Any

from .profiles import ModelCatalog, ModelProfile
from .router import RoutingError


def build_chat_model(profile: ModelProfile) -> Any:
    ready, _ = ModelCatalog.availability(profile)
    if not ready:
        raise RoutingError(
            "Selected model is not configured", status_code=409, code="model_not_configured"
        )
    if profile.provider == "demo":
        from core.orchestrator.demo import DemoChatModel

        return DemoChatModel(profile_id=profile.id)
    key = os.getenv(profile.api_key_env, "") if profile.api_key_env else "local-key-not-required"
    common: dict[str, Any] = {
        "model": profile.model_name(),
        "api_key": key,
        "timeout": 60,
        "max_retries": 0,
    }
    endpoint = profile.endpoint()
    if profile.provider == "openai-compatible":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            **common, base_url=endpoint, streaming=True, max_tokens=profile.max_output_tokens
        )
    if profile.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            **common, base_url=endpoint, streaming=True, max_tokens=profile.max_output_tokens
        )
    if profile.provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if endpoint:
            common["base_url"] = endpoint
        return ChatGoogleGenerativeAI(**common, max_output_tokens=profile.max_output_tokens)
    from langchain_community.chat_models import ChatTongyi

    return ChatTongyi(
        model_name=profile.model_name(),
        dashscope_api_key=key,
        streaming=True,
        max_tokens=profile.max_output_tokens,
    )
