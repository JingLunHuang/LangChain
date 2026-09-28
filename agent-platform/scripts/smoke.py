"""Real localhost API smoke test; generated credentials never enter output."""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    key = secrets.token_urlsafe(32)
    state = ROOT / ".state"
    state.mkdir(exist_ok=True)
    db = state / ("smoke-" + secrets.token_hex(6) + ".sqlite3")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    environment = {
        **os.environ,
        "AGENT_PLATFORM_DEMO": "1",
        "PLATFORM_API_KEYS": key + ":smoke",
        "PLATFORM_KEY_DB": str(db),
        "LANGSMITH_TRACING": "false",
    }
    # Ignore ambient production connectors in the self-contained demo.
    for name in ["PLATFORM_MCP_SERVERS", "AGENT_PLATFORM_TENANT_DOCS", "AGENT_PLATFORM_DOCS_PATH"]:
        environment.pop(name, None)
    with subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "platform_api.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) as process:
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=30
            ) as client:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("API exited before readiness")
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError("API failed readiness check")
                assert client.post("/v1/invoke", json={"message": "hello"}).status_code == 401
                headers = {"X-API-Key": key}
                response = client.post(
                    "/v1/invoke",
                    headers=headers,
                    json={"message": "What is KV cache PagedAttention?"},
                )
                response.raise_for_status()
                assert "cache.md" in response.json()["output"]
                sid = response.json()["session_id"]
                followup = client.post(
                    "/v1/invoke",
                    headers=headers,
                    json={"message": "MCP platform", "session_id": sid},
                )
                followup.raise_for_status()
                with client.stream(
                    "POST",
                    "/v1/stream",
                    headers=headers,
                    json={"message": "KV cache", "session_id": sid},
                ) as stream:
                    stream.raise_for_status()
                    deltas, completed = 0, False
                    for line in stream.iter_lines():
                        if line.startswith('data: {"delta"'):
                            deltas += 1
                        if line == "data: [DONE]":
                            completed = True
                assert deltas > 1 and completed
                result = {
                    "health": "passed",
                    "auth": "passed",
                    "hybrid_retrieval": "passed",
                    "session_followup": "passed",
                    "stream_deltas": deltas,
                    "done": completed,
                }
                report = ROOT / "reports" / "http-smoke.json"
                report.parent.mkdir(exist_ok=True)
                report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
                print(json.dumps(result))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            db.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
