"""示例 01：平臺化工具鏈 Agent


（文字分析 / 資料轉換 / 統計行數 / 查找文字 / 替換文字 共 5 個 @tool）

新架構改進點：
- 不再直接呼叫 langchain.agents.create_agent，改由編排層
  core.orchestrator.create_platform_agent(tools=...) 統一建立 Agent，
  與平臺接入層（platform_api/api.py）共用同一套調度邏輯；
- LLM 實例由編排層按平臺預設配置注入，示例不再關心 ChatTongyi 的初始化細節；
- 非同步優先：使用 ainvoke 呼叫 Agent，便於後續接入 /v1/invoke、/v1/stream 端點。

執行方式（在 agent-platform 根目錄下）：
    python examples/01_toolchain_agent.py
"""

import asyncio
import csv
import io
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.tools import tool

from core.orchestrator.agent import create_platform_agent


@tool
def text_analysis(text: str) -> str:
    """分析文字內容，提取字數、字元數和情感傾向

    參數:
        text: 要分析的文字
    回傳:
        分析結果
    """
    word_count = len(text.split())
    char_count = len(text)

    positive_words = ["好", "優秀", "喜歡", "快樂", "成功", "美好"]
    negative_words = ["差", "糟糕", "討厭", "悲傷", "失敗", "痛苦"]

    positive_count = sum(1 for word in positive_words if word in text)
    negative_count = sum(1 for word in negative_words if word in text)

    sentiment = (
        "積極"
        if positive_count > negative_count
        else "消極"
        if negative_count > positive_count
        else "中性"
    )

    return f"文本分析結果:\n- 字數: {word_count}\n- 字符數: {char_count}\n- 情感傾向: {sentiment}"


@tool
def data_conversion(input_data: str, input_format: str, output_format: str) -> str:
    """在不同資料格式之間轉換，如JSON、CSV等

    參數:
        input_data: 輸入資料
        input_format: 輸入格式
        output_format: 輸出格式
    回傳:
        轉換後的資料
    """
    try:
        if input_format.lower() == "json" and output_format.lower() == "csv":
            data = json.loads(input_data)
            if isinstance(data, list):
                if not data:
                    return "空數據"

                if not all(isinstance(item, dict) for item in data):
                    return "輸入數據必須是JSON對象數組"
                headers = sorted({header for item in data for header in item})
                output = io.StringIO(newline="")
                writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
                writer.writeheader()
                writer.writerows(data)
                return output.getvalue()
            return "輸入數據必須是JSON數組"

        if input_format.lower() == "csv" and output_format.lower() == "json":
            reader = csv.DictReader(io.StringIO(input_data, newline=""))
            result = list(reader)
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                return "CSV 標題缺失或重複"
            if any(None in row or any(value is None for value in row.values()) for row in result):
                return "CSV 數據行與標題列數不一致"
            return json.dumps(result, ensure_ascii=False, indent=2)

        return f"不支持的轉換: {input_format} -> {output_format}"

    except Exception as e:
        return f"轉換失敗: {str(e)}"


@tool
def count_lines(content: str) -> str:
    """統計文字內容的行數

    參數:
        content: 文字內容
    回傳:
        行數統計結果
    """
    return f"文本共有 {len(content.splitlines())} 行"


@tool
def find_text(content: str, search_text: str) -> str:
    """在文字內容中查找指定文字

    參數:
        content: 文字內容
        search_text: 要查找的文字
    回傳:
        查找結果
    """
    if not search_text:
        return "請提供要查找的文本"

    matches = [
        f"第 {i + 1} 行: {line}"
        for i, line in enumerate(content.splitlines())
        if search_text in line
    ]

    if matches:
        return f"找到 {len(matches)} 處匹配:\n" + "\n".join(matches)
    return f"未找到文本 '{search_text}'"


@tool
def replace_text(content: str, old_text: str, new_text: str) -> str:
    """在文字內容中替換指定文字

    參數:
        content: 文字內容
        old_text: 要替換的舊文字
        new_text: 替換後的新文字
    回傳:
        替換結果
    """
    if not old_text:
        return "請提供要替換的文本"

    count = content.count(old_text)
    new_content = content.replace(old_text, new_text)

    return f"替換完成，共替換 {count} 處。\n新內容:\n{new_content}"


TOOLS = [text_analysis, data_conversion, count_lines, find_text, replace_text]


def _require_api_key() -> str:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("錯誤：未檢測到環境變量 DASHSCOPE_API_KEY。")
        print("請先設置 DashScope API Key，例如：")
        print('  export DASHSCOPE_API_KEY="sk-..."   # Git Bash / Linux / macOS')
        print("  set DASHSCOPE_API_KEY=sk-...        # Windows CMD")
        sys.exit(1)
    return api_key


async def process_task(agent, task_description: str) -> str:
    result = await agent.ainvoke({"messages": [("user", task_description)]})
    return result["messages"][-1].content


async def main() -> None:
    _require_api_key()
    agent = create_platform_agent(tools=TOOLS)

    task1 = (
        "分析以下文本的情感傾向，並統計其中的行數："
        "'這個產品非常好用，我很喜歡它的設計，使用體驗非常棒！\n"
        "價格也很合理，推薦大家購買。\n客服態度也很好，解答問題很及時。'"
    )
    print("任務1:", task1)
    print("結果:", await process_task(agent, task1))

    task2 = (
        "將以下CSV數據轉換爲JSON格式："
        "'name,age,comment\n張三,25,這個產品很好\n李四,30,服務態度差\n王五,28,性價比高'"
    )
    print("\n任務2:", task2)
    print("結果:", await process_task(agent, task2))


if __name__ == "__main__":
    asyncio.run(main())
