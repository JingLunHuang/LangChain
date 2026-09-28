"""API、MCP 與 CLI 共用的請求驗證與路由參數。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .profiles import Preference, TaskType


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(default="default", min_length=1, max_length=64)
    model_id: str | None = Field(default=None, min_length=1, max_length=64)
    preference: Preference | None = None
    max_cost_tier: int | None = Field(default=None, ge=1, le=3)


class InvokeRequest(ModelRequest):
    message: str = Field(min_length=1, max_length=16000)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    task: TaskType | None = None

    @field_validator("message")
    @classmethod
    def nonblank_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value

    def routing(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "preference": self.preference,
            "task_hint": self.task,
            "max_cost_tier": self.max_cost_tier,
        }


class SwitchRequest(ModelRequest):
    session_id: str = Field(min_length=1, max_length=128)
