import importlib
import json
import sys

import pytest

from mcp_server.client import MCPConnection, connect


def test_course_csv_conversion_preserves_quotes_commas_and_newlines() -> None:
    module = importlib.import_module("examples.01_toolchain_agent")
    rows = [{"name": "張三", "comment": '好用, "推薦"\n第二行', "age": "25"}]
    converted = module.data_conversion.invoke(
        {
            "input_data": json.dumps(rows, ensure_ascii=False),
            "input_format": "json",
            "output_format": "csv",
        }
    )
    back = module.data_conversion.invoke(
        {"input_data": converted, "input_format": "csv", "output_format": "json"}
    )
    assert json.loads(back) == rows
    assert converted.startswith("age,comment,name\n")


def test_invalid_csv_is_not_silently_dropped() -> None:
    module = importlib.import_module("examples.01_toolchain_agent")
    result = module.data_conversion.invoke(
        {"input_data": "a,b\n1,2,3", "input_format": "csv", "output_format": "json"}
    )
    assert "不一致" in result


@pytest.mark.asyncio
async def test_network_example_mcp_tools_and_stdout_cleanliness() -> None:
    config = MCPConnection(
        name="diagnosis",
        command=sys.executable,
        args=["-m", "examples.02_network_diagnosis", "--mcp"],
        env={"PYTHONIOENCODING": "utf-8"},
    )
    async with connect(config) as session:
        tools = await session.list_tools()
        assert len(tools.tools) == 4
        result = await session.call_tool("ping_tool", {"target": "127.0.0.1"})
        assert not result.isError and "<1ms" in result.content[0].text
