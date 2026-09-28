import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.orchestrator.runtime import AgentRuntime
from platform_api.api import create_app
from platform_api.auth import KeyStore


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_API_KEYS", "test-alpha:a,test-beta:b")
    monkeypatch.setenv("PLATFORM_ADMIN_KEY", "test-administrator")
    runtime = AgentRuntime()
    runtime.configs["private"] = {"tenant_ids": ["a"], "tools": []}
    app = create_app(runtime=runtime, key_store=KeyStore(tmp_path / "keys.sqlite3"))
    with TestClient(app) as c:
        yield c


def post(client: TestClient, message: str, *, key: str = "test-alpha", **kwargs):
    return client.post(
        "/v1/invoke",
        json={"message": message, "agent_id": "chat", **kwargs},
        headers={"X-API-Key": key},
    )


def test_health_auth_and_no_implicit_default_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/v1/invoke", json={"message": "hello"}).status_code == 401
    assert post(client, "hello", key="wrong").status_code == 401
    monkeypatch.delenv("PLATFORM_API_KEYS")
    assert post(client, "hello", key="dev-key-change-me").status_code == 401


def test_real_agent_memory_isolated_by_tenant_agent_and_session(client: TestClient) -> None:
    for key, sid, aid, text in [
        ("test-alpha", "same", "chat", "a1"),
        ("test-beta", "same", "chat", "b1"),
        ("test-alpha", "same", "private", "p1"),
        ("test-alpha", "other", "chat", "o1"),
        ("test-alpha", "same", "chat", "a2"),
    ]:
        response = post(client, text, key=key, session_id=sid, agent_id=aid)
        assert response.status_code == 200, response.text
    sessions = client.app.state.runtime.sessions
    assert [m["content"] for m in sessions[("a", "chat", "same")].history[::2]] == ["a1", "a2"]
    assert len(sessions[("b", "chat", "same")].history) == 2
    assert len(sessions[("a", "private", "same")].history) == 2
    assert len(sessions[("a", "chat", "other")].history) == 2


def test_agent_permissions_and_request_schema(client: TestClient) -> None:
    assert post(client, "q", agent_id="missing").status_code == 404
    assert post(client, "q", key="test-beta", agent_id="private").status_code == 404
    assert post(client, "").status_code == 422
    assert (
        client.post(
            "/v1/invoke", json={"input": "wrong field"}, headers={"X-API-Key": "test-alpha"}
        ).status_code
        == 422
    )


def test_real_stream_multiple_deltas_done_and_committed_history(client: TestClient) -> None:
    response = client.post(
        "/v1/stream",
        json={"message": "x" * 70, "agent_id": "chat", "session_id": "stream"},
        headers={"X-API-Key": "test-alpha"},
    )
    assert response.status_code == 200
    deltas = [
        json.loads(line[6:])["delta"]
        for line in response.text.splitlines()
        if line.startswith('data: {"delta"')
    ]
    assert len(deltas) > 1
    assert "".join(deltas) == "[Offline demo] " + "x" * 70
    assert response.text.endswith("data: [DONE]\n\n")
    assert len(client.app.state.runtime.sessions[("a", "chat", "stream")].history) == 2


def test_oversized_prompt_returns_413_for_both_routes(client: TestClient) -> None:
    for endpoint in ["/v1/invoke", "/v1/stream"]:
        response = client.post(
            endpoint,
            json={"message": "中文" * 1000, "agent_id": "chat"},
            headers={"X-API-Key": "test-alpha"},
        )
        assert response.status_code == 413


def test_full_api_agent_uses_actual_hybrid_retrieval(client: TestClient) -> None:
    response = post(client, "What is KV cache PagedAttention?", agent_id="default")
    assert response.status_code == 200, response.text
    assert "PagedAttention" in response.json()["output"]
    assert "cache.md" in response.json()["output"]


def test_durable_key_issue_list_revoke_and_admin_auth(client: TestClient, tmp_path: Path) -> None:
    assert client.post("/v1/keys", json={"tenant_id": "new"}).status_code == 403
    admin = {"X-Admin-Key": "test-administrator"}
    issued = client.post("/v1/keys", json={"tenant_id": "new", "label": "test"}, headers=admin)
    assert issued.status_code == 201
    raw, key_id = issued.json()["api_key"], issued.json()["id"]
    listing = client.get("/v1/keys", headers=admin)
    assert raw not in listing.text and "digest" not in listing.text
    store = KeyStore(tmp_path / "keys.sqlite3")
    assert store.authenticate(raw).tenant_id == "new"
    assert raw.encode() not in (tmp_path / "keys.sqlite3").read_bytes()
    assert post(client, "hello", key=raw).status_code == 200
    assert client.delete("/v1/keys/" + key_id, headers=admin).status_code == 200
    assert post(client, "hello", key=raw).status_code == 401
