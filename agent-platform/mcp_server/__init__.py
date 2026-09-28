"""agent-platform 協議層：原生 MCP Server 模組。"""

__all__ = ["create_server", "register_tools"]


def __getattr__(name: str):
    if name == "create_server":
        from mcp_server.server import create_server

        return create_server
    if name == "register_tools":
        from mcp_server.registry import register_tools

        return register_tools
    raise AttributeError(name)
