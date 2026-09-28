"""OmniAgent / OmniRoute MCP Server 入口。

用法:
    python -m mcp_server.server --transport stdio
    python -m mcp_server.server --transport sse --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
from typing import Any

from mcp.server.fastmcp import FastMCP

from core.orchestrator.runtime import AgentRuntime
from mcp_server.registry import register_tools

logger = logging.getLogger(__name__)

SERVER_NAME = "omniagent-platform"


def register_resources(server: FastMCP) -> None:
    """Resource 擴充點：在此按同樣模式追加自定義 Resource。

    示例：
        @server.resource("config://platform")
        def platform_config() -> str:
            return '{"model": "qwen-turbo"}'
    """

    @server.resource("info://server")
    def server_info() -> str:
        return f"{SERVER_NAME} MCP Server"


def register_prompts(server: FastMCP) -> None:
    """Prompt 擴充點：在此按同樣模式追加自定義 Prompt 模板。

    示例：
        @server.prompt()
        def summarize(text: str) -> str:
            return f"請總結以下內容：{text}"
    """

    @server.prompt()
    def diagnose(target: str) -> str:
        return f"請調用可用工具對 {target} 做健康診斷，並給出結論。"


def create_server() -> FastMCP:
    # Load native data dependencies before stdio starts its blocking reader threads.
    from llama_index.core import VectorStoreIndex  # noqa: F401

    server = FastMCP(SERVER_NAME, stateless_http=True, json_response=True)
    register_tools(server, AgentRuntime())
    register_resources(server)
    register_prompts(server)
    return server


def create_network_app(server: FastMCP, transport: str) -> Any:
    """An operator-scoped MCP endpoint with a separate explicit access key."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    class KeyGate(BaseHTTPMiddleware):
        async def dispatch(self, request: Any, call_next: Any) -> Any:
            expected = os.getenv("PLATFORM_MCP_KEY")
            supplied = request.headers.get("X-API-Key", "")
            if not expected or not secrets.compare_digest(supplied, expected):
                return JSONResponse({"error": "MCP access key required"}, status_code=401)
            return await call_next(request)

    app = server.sse_app() if transport == "sse" else server.streamable_http_app()
    app.add_middleware(KeyGate)
    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="mcp_server", description="OmniAgent / OmniRoute MCP Server"
    )
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1", help="SSE 模式監聽地址")
    parser.add_argument("--port", type=int, default=8000, help="SSE 模式監聽端口")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    server = create_server()
    if args.transport != "stdio":
        import uvicorn

        server.settings.host = args.host
        server.settings.port = args.port
        uvicorn.run(create_network_app(server, args.transport), host=args.host, port=args.port)
    else:
        logger.info("Starting stdio transport")
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
