# 原生 MCP Server / Client

Server 使用固定版本範圍的官方 MCP Python SDK v1；支援 stdio、相容性 SSE、Streamable HTTP。Tools、Resources 與 Prompts 由型別化函數註冊。[官方 SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)

## 介面

| 名稱 | 合約 |
| --- | --- |
| `ping` | 無參數；回傳 pong |
| `hybrid_retrieve` | `query: str`；回傳 JSON 文字，含 answer 及 sources |
| `agent_invoke` | message、可選 session_id、agent_id；回傳答案與 session_id |
| `info://server` | resource：服務名稱 |
| `diagnose` | prompt：target 主機名稱 |

資料目錄由 `AGENT_PLATFORM_DOCS_PATH` 設定，不接受 client 指定的 docs_path。Server instance 內索引只建立一次，並用鎖防止同時重建。

## 連接方式

```powershell
$env:AGENT_PLATFORM_DEMO='1'
uv run python -m mcp_server.server --transport stdio
```

stdio 不會自動繼承父程序全部環境變數；設定 `MCPConnection.env` 中必要的模型／知識庫設定。傳輸 stdout 僅保留協議 JSON，日誌使用 stderr。

網路入口需設定 `PLATFORM_MCP_KEY`，Client 使用相同值作為 `X-API-Key`。不要將 Key 寫進 committed 設定範例。

```powershell
uv run python -m mcp_server.server --transport sse --port 8002
uv run python -m mcp_server.server --transport streamable-http --port 8001
```

Client URL 為 `http://127.0.0.1:8002/sse` 或 `http://127.0.0.1:8001/mcp`。這是操作者範圍的 MCP，不將 HTTP MCP Key 映射成 API 租戶；需多租戶權限時使用平臺 API。

```python
from mcp_server.client import MCPConnection, connect, as_langchain_tools

config = MCPConnection(
    name="knowledge",
    transport="streamable-http",
    url="http://127.0.0.1:8001/mcp",
    headers={"X-API-Key": mcp_key},
)
async with connect(config) as session:
    tools = await as_langchain_tools(session, config.name)
    # tools 保留 MCP JSON schema，名稱加 namespace 避免衝突。
    result = await tools[0].ainvoke(arguments)
```

Session 必須在 context manager 存活期間使用。Adapter 的工具名例如 `knowledge__hybrid_retrieve`，不通過 exec 重建任意 schema，工具錯誤會回報 exception。

## 為 API 接外部 MCP 工具

`PLATFORM_MCP_SERVERS` 是 JSON connection 陣列。例如只讀、本機、共享的知識服務：

```json
[{"name":"knowledge","transport":"stdio","command":"python","args":["-m","mcp_server.server"],"env":{"AGENT_PLATFORM_DEMO":"1"}}]
```

Windows 建議 command 使用虛擬環境 python.exe 的完整路徑。FastAPI lifespan 負責連接、載入工具與關閉 session；這些工具由操作者決定，作為 API 的共享能力。不要將某租戶私有服務直接接成全部租戶可用的共享工具。

## 擴充與驗證

在 `registry.py` 註冊新的型別化函數；resource / prompt 擴充入口位於 `server.py`。額外的網路診斷工具可透過 `uv run python examples/02_network_diagnosis.py --mcp` 提供。

```powershell
uv run pytest tests/test_mcp_compat.py
uv run python -m examples.04_mcp_client
```

相容性測試啟動真正子程序／本機 HTTP 服務，涵蓋三種 transport 的握手、tool 清單、實際檢索、錯誤、resource、prompt 和 agent_invoke。
