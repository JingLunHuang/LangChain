"""All tests use the offline demo; no provider credentials or trace exports."""

import pytest


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_DEMO", "1")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.delenv("PLATFORM_MCP_SERVERS", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_TENANT_DOCS", raising=False)
