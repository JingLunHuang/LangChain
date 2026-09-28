"""示例 02：網路故障診斷 Agent（工具可插拔版）

課程來源：CASE-搭建故障诊断Agent/2-network_diagnosis_agent.py
（ping / DNS 解析 / 介面檢查 / 日誌分析 共 4 個模擬診斷工具）

新架構改進點：
- Agent 改由編排層 core.orchestrator.create_platform_agent(tools=...) 建立，
  與平臺接入層共用同一套調度邏輯；
- 工具不再散落在腳本里，而是集中到 DIAGNOSIS_TOOLS 註冊表：新增診斷工具
  只需往註冊表加一項，Agent 與 MCP Server 即可同時獲得該能力（即插即用）；
- 演示協議層理念：同一批工具既可直接注入平臺 Agent，也可通過
  mcp_server.registry.register_tools(server) 掛載到 MCP Server。
  執行 `python examples/02_network_diagnosis.py --mcp` 會以 stdio 方式
  啟動一個最小 MCP Server，對外暴露全部診斷工具。

執行方式（在 agent-platform 根目錄下）：
    python examples/02_network_diagnosis.py         # 平臺 Agent 診斷演示
    python examples/02_network_diagnosis.py --mcp   # 以 MCP stdio Server 暴露工具
"""

import asyncio
import os
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.tools import tool

from core.orchestrator.agent import create_platform_agent


@tool
def ping_tool(target: str) -> str:
    """模擬到指定主機或 IP 的連通性與延遲；不代表實際測量。

    參數:
        target: 目標主機名或 IP 地址
    回傳:
        模擬的 ping 結果
    """
    print(f"--- 模擬執行 Ping: {target} ---", file=sys.stderr)
    if "unreachable" in target or target == "192.168.1.254":
        return f"Ping {target} 失敗：請求超時。"
    if target == "localhost" or target == "127.0.0.1":
        return f"Ping {target} 成功：延遲 <1ms。"
    if "example.com" in target:
        delay = random.randint(20, 80)
        return f"Ping {target} 成功：延遲 {delay}ms。"
    delay = random.randint(5, 50)
    return f"Ping {target} 成功：延遲 {delay}ms。"


@tool
def dns_tool(hostname: str) -> str:
    """模擬主機名稱的 DNS 解析。

    參數:
        hostname: 要解析的主機名
    回傳:
        模擬的 DNS 解析結果
    """
    print(f"--- 模擬 DNS 查詢: {hostname} ---", file=sys.stderr)
    if hostname == "www.example.com":
        return f"DNS 解析 {hostname} 成功：IP 地址是 93.184.216.34"
    if hostname == "internal.service.local":
        return f"DNS 解析 {hostname} 成功：IP 地址是 192.168.1.100"
    if hostname == "unknown.domain.xyz":
        return f"DNS 解析 {hostname} 失敗：找不到主機。"
    if hostname == "127.0.0.1" or re.match(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", hostname):
        return f"輸入 '{hostname}' 已經是 IP 地址，無需 DNS 解析。"
    return f"DNS 解析 {hostname} 成功：IP 地址是 10.0.0.5"


@tool
def interface_check_tool(interface_name: str | None = None) -> str:
    """模擬網路介面狀態；未指定名稱時使用預設介面。

    參數:
        interface_name: (可選) 要檢查的介面名稱
    回傳:
        模擬的介面狀態資訊
    """
    print(f"--- 模擬檢查接口狀態: {interface_name or '默認接口'} ---", file=sys.stderr)
    if interface_name and "eth1" in interface_name.lower():
        return f"接口 '{interface_name}' 狀態：關閉 (Administratively down)"
    return (
        "接口 'Ethernet'/'Wi-Fi' 狀態：啓用, IP 地址: 192.168.1.50, "
        "子網掩碼: 255.255.255.0, 網關: 192.168.1.1"
    )


@tool
def log_analysis_tool(keywords: str, time_range: str | None = "過去1小時") -> str:
    """以關鍵字及時間範圍模擬搜尋網路錯誤日誌。

    參數:
        keywords: 用於搜索日誌的關鍵詞
        time_range: (可選) 要搜索的時間範圍描述，預設為 '過去1小時'
    回傳:
        模擬的日誌分析結果
    """
    print(f"--- 模擬分析日誌: 關鍵詞='{keywords}', 時間範圍='{time_range}' ---", file=sys.stderr)
    keywords_lower = keywords.lower()
    if "timeout" in keywords_lower or "超時" in keywords_lower:
        return (
            f"在 {time_range} 的日誌中找到 3 條與 '{keywords}' 相關的條目：\n"
            f"- [Error] 連接到 10.0.0.88:8080 超時\n"
            f"- [Warning] 對 api.external.com 的請求超時\n"
            f"- [Error] 內部服務通信超時"
        )
    if "connection refused" in keywords_lower or "連接被拒絕" in keywords_lower:
        return (
            f"在 {time_range} 的日誌中找到 1 條與 '{keywords}' 相關的條目：\n"
            f"- [Error] 連接到 192.168.1.200:5432 失敗：Connection refused"
        )
    if "dns" in keywords_lower:
        return (
            f"在 {time_range} 的日誌中找到 2 條與 '{keywords}' 相關的條目：\n"
            f"- [Warning] DNS 服務器 8.8.8.8 響應慢\n"
            f"- [Error] 無法解析主機名 'failed.internal.service'"
        )
    return f"在 {time_range} 的日誌中未找到與 '{keywords}' 相關的明顯網絡錯誤條目。"


# 工具註冊表：Agent 與 MCP Server 共用同一份清單，新增工具只需在此追加
DIAGNOSIS_TOOLS = [ping_tool, dns_tool, interface_check_tool, log_analysis_tool]


def _require_api_key() -> str:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("錯誤：未檢測到環境變量 DASHSCOPE_API_KEY。")
        print("請先設置 DashScope API Key，例如：")
        print('  export DASHSCOPE_API_KEY="sk-..."   # Git Bash / Linux / macOS')
        print("  set DASHSCOPE_API_KEY=sk-...        # Windows CMD")
        sys.exit(1)
    return api_key


def run_mcp_stdio_server() -> None:
    """以 MCP stdio Server 方式暴露診斷工具，演示協議層的工具即插即用。

    生產環境請使用 `python -m mcp_server.server --transport stdio|sse`，
    由 mcp_server/registry.py 的 register_tools(server) 統一掛載工具。
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("錯誤：未安裝 mcp 包，無法啓動 MCP Server。請先安裝依賴：uv add mcp")
        sys.exit(1)

    mcp_server = FastMCP("network-diagnosis")
    for diag_tool in DIAGNOSIS_TOOLS:
        mcp_server.add_tool(diag_tool.func, name=diag_tool.name, description=diag_tool.description)
    print(
        "MCP Server (stdio) 已啓動，已註冊工具: " + ", ".join(t.name for t in DIAGNOSIS_TOOLS),
        file=sys.stderr,
    )
    mcp_server.run(transport="stdio")


async def diagnose(agent, issue_description: str) -> str:
    print(f"\n--- 開始診斷任務 ---\n用戶問題: {issue_description}")
    result = await agent.ainvoke({"messages": [("user", issue_description)]})
    return result["messages"][-1].content


async def main() -> None:
    _require_api_key()
    agent = create_platform_agent(tools=DIAGNOSIS_TOOLS)

    task1 = "我無法訪問 www.example.com，瀏覽器顯示連接超時。"
    print("診斷任務 1:")
    print(f"最終診斷結果: {await diagnose(agent, task1)}")

    print("\n" + "=" * 50 + "\n")

    task2 = "連接到內部數據庫服務器 (internal.service.local) 失敗，提示 'connection refused'。"
    print("診斷任務 2:")
    print(f"最終診斷結果: {await diagnose(agent, task2)}")


if __name__ == "__main__":
    if "--mcp" in sys.argv:
        run_mcp_stdio_server()
    else:
        asyncio.run(main())
