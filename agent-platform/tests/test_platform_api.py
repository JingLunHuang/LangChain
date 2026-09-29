"""接入層端到端測試：鑑權、離線預覽、路由決策、會話固定模型、SSE 與租戶隔離。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.orchestrator.runtime import AgentRuntime
from platform_api.api import create_app
from platform_api.auth import KeyStore

ADMIN_KEY = "test-admin-key"
BOOTSTRAP_KEY = "test-bootstrap-key"
ADMIN_HEADERS = {"X-Admin-Key": ADMIN_KEY}
BOOTSTRAP_HEADERS = {"X-API-Key": BOOTSTRAP_KEY}
DEMO_MODEL_IDS = {"demo-fast", "demo-coder", "demo-reasoner", "demo-writer"}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    monkeypatch.setenv("AGENT_PLATFORM_DEMO", "1")
    monkeypatch.setenv("PLATFORM_ADMIN_KEY", ADMIN_KEY)
    monkeypatch.setenv("PLATFORM_API_KEYS", f"{BOOTSTRAP_KEY}:bootstrap")
    monkeypatch.setenv("PLATFORM_KEY_DB", str(tmp_path / "keys.sqlite3"))
    store = KeyStore(tmp_path / "keys.sqlite3")
    app = create_app(runtime=AgentRuntime(), key_store=store)
    with TestClient(app) as test_client:
        yield test_client


def issue_key(client: TestClient, tenant: str, label: str = "") -> dict[str, str]:
    response = client.post(
        "/v1/keys", json={"tenant_id": tenant, "label": label}, headers=ADMIN_HEADERS
    )
    assert response.status_code == 201
    return response.json()


def auth_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def test_health_requires_no_key(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_demo_preview_endpoints_require_no_key(client: TestClient) -> None:
    models = client.get("/demo/models")
    assert models.status_code == 200
    assert {item["id"] for item in models.json()} == DEMO_MODEL_IDS
    assert all(item["available"] for item in models.json())

    route = client.post("/demo/route", json={"message": "介紹一下平台", "agent_id": "default"})
    assert route.status_code == 200
    body = route.json()
    assert body["preview"] is True
    assert body["model_id"] in DEMO_MODEL_IDS
    assert body["mode"] == "auto"
    assert body["decision_id"]

    missing = client.post("/demo/route", json={"message": "hi", "agent_id": "ghost"})
    assert missing.status_code == 404


def test_invoke_rejects_missing_or_invalid_key(client: TestClient) -> None:
    payload = {"message": "hi", "agent_id": "chat"}
    assert client.post("/v1/invoke", json=payload).status_code == 401
    assert (
        client.post("/v1/invoke", json=payload, headers=auth_headers("ap_forged")).status_code
        == 401
    )


def test_admin_issues_tenant_key_and_invoke_returns_route(client: TestClient) -> None:
    assert client.post("/v1/keys", json={"tenant_id": "alpha"}).status_code == 403
    assert (
        client.post(
            "/v1/keys", json={"tenant_id": "alpha"}, headers={"X-Admin-Key": "wrong"}
        ).status_code
        == 403
    )

    issued = issue_key(client, "alpha", label="第一把")
    assert issued["api_key"].startswith("ap_")
    assert issued["tenant_id"] == "alpha"

    listed = client.get("/v1/keys", headers=ADMIN_HEADERS)
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [issued["id"]]

    response = client.post(
        "/v1/invoke",
        json={"message": "平台支援哪些功能？", "agent_id": "default"},
        headers=auth_headers(issued["api_key"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "alpha"
    assert body["agent_id"] == "default"
    assert body["session_id"]
    assert isinstance(body["output"], str) and body["output"]
    route = body["route"]
    assert route["model_id"] in DEMO_MODEL_IDS
    assert route["mode"] == "auto"
    assert route["decision_id"]
    assert route["task"]["task"]


def test_revoked_key_can_no_longer_invoke(client: TestClient) -> None:
    issued = issue_key(client, "beta")
    headers = auth_headers(issued["api_key"])
    payload = {"message": "hi", "agent_id": "chat"}
    assert client.post("/v1/invoke", json=payload, headers=headers).status_code == 200

    revoked = client.delete(f"/v1/keys/{issued['id']}", headers=ADMIN_HEADERS)
    assert revoked.status_code == 200
    assert revoked.json() == {"revoked": True}

    assert client.post("/v1/invoke", json=payload, headers=headers).status_code == 401
    assert client.delete("/v1/keys/does-not-exist", headers=ADMIN_HEADERS).status_code == 404
    assert client.delete(f"/v1/keys/{issued['id']}").status_code == 403


def test_route_preview_and_session_model_pinning(client: TestClient) -> None:
    preview = client.post(
        "/v1/route", json={"message": "hi", "agent_id": "chat"}, headers=BOOTSTRAP_HEADERS
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["mode"] == "auto"
    session_id = body["session_id"]

    pinned = client.post(
        "/v1/sessions/model",
        json={"agent_id": "chat", "session_id": session_id, "model_id": "demo-reasoner"},
        headers=BOOTSTRAP_HEADERS,
    )
    assert pinned.status_code == 200
    assert pinned.json()["mode"] == "session"
    assert pinned.json()["model_id"] == "demo-reasoner"

    follow_up = client.post(
        "/v1/route",
        json={"message": "continue", "agent_id": "chat", "session_id": session_id},
        headers=BOOTSTRAP_HEADERS,
    )
    assert follow_up.status_code == 200
    assert follow_up.json()["mode"] == "session"
    assert follow_up.json()["model_id"] == "demo-reasoner"

    restored = client.post(
        "/v1/sessions/model",
        json={"agent_id": "chat", "session_id": session_id, "model_id": "auto"},
        headers=BOOTSTRAP_HEADERS,
    )
    assert restored.status_code == 200
    assert restored.json()["mode"] == "auto"
    assert restored.json()["model_id"] is None

    back = client.post(
        "/v1/route",
        json={"message": "continue", "agent_id": "chat", "session_id": session_id},
        headers=BOOTSTRAP_HEADERS,
    )
    assert back.status_code == 200
    assert back.json()["mode"] == "auto"


def test_stream_returns_sse_frames(client: TestClient) -> None:
    issued = issue_key(client, "streamer")
    response = client.post(
        "/v1/stream",
        json={"message": "講個笑話", "agent_id": "chat"},
        headers=auth_headers(issued["api_key"]),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: session\n" in body
    assert "event: route\n" in body
    assert body.rstrip().endswith("data: [DONE]")

    frames = [chunk for chunk in body.split("\n\n") if chunk.strip()]
    session_frame = next(chunk for chunk in frames if chunk.startswith("event: session"))
    session_id = json.loads(session_frame.split("data: ", 1)[1])["session_id"]
    assert session_id
    route_frame = next(chunk for chunk in frames if chunk.startswith("event: route"))
    route = json.loads(route_frame.split("data: ", 1)[1])
    assert route["model_id"] in DEMO_MODEL_IDS
    assert route["decision_id"]


def test_unknown_agent_returns_404(client: TestClient) -> None:
    payload = {"message": "hi", "agent_id": "ghost"}
    assert client.post("/v1/invoke", json=payload, headers=BOOTSTRAP_HEADERS).status_code == 404
    assert client.post("/v1/route", json=payload, headers=BOOTSTRAP_HEADERS).status_code == 404
    assert (
        client.post(
            "/v1/sessions/model",
            json={"agent_id": "ghost", "session_id": "s1", "model_id": "demo-fast"},
            headers=BOOTSTRAP_HEADERS,
        ).status_code
        == 404
    )
    assert client.get("/v1/models", headers=BOOTSTRAP_HEADERS).status_code == 200
    assert (
        client.get(
            "/v1/models", params={"agent_id": "ghost"}, headers=BOOTSTRAP_HEADERS
        ).status_code
        == 404
    )


def test_routing_traces_are_isolated_per_tenant(client: TestClient) -> None:
    alpha = issue_key(client, "alpha")
    beta = issue_key(client, "beta")
    for key in (alpha["api_key"], beta["api_key"]):
        response = client.post(
            "/v1/invoke",
            json={"message": "hi", "agent_id": "chat"},
            headers=auth_headers(key),
        )
        assert response.status_code == 200

    assert client.get("/v1/routing/traces").status_code == 401
    alpha_traces = client.get("/v1/routing/traces", headers=auth_headers(alpha["api_key"]))
    beta_traces = client.get("/v1/routing/traces", headers=auth_headers(beta["api_key"]))
    assert alpha_traces.status_code == 200
    assert beta_traces.status_code == 200
    assert len(alpha_traces.json()) >= 1
    assert len(beta_traces.json()) >= 1
    assert {item["tenant_id"] for item in alpha_traces.json()} == {"alpha"}
    assert {item["tenant_id"] for item in beta_traces.json()} == {"beta"}
    assert {item["session_id"] for item in alpha_traces.json()}.isdisjoint(
        {item["session_id"] for item in beta_traces.json()}
    )
