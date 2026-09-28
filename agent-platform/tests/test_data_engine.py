import asyncio
import json
from pathlib import Path

import pytest
from llama_index.core.llms import MockLLM
from llama_index.core.schema import TextNode

from core.data_engine.engine import (
    DEFAULT_DOCS_PATH,
    as_langchain_tool,
    as_mcp_tool_spec,
    build_query_engine,
)
from core.data_engine.retrieval import DemoEmbedding, LexicalRetriever


@pytest.mark.asyncio
async def test_actual_hybrid_query_and_langchain_tool_return_sources() -> None:
    engine = await asyncio.to_thread(build_query_engine, DEFAULT_DOCS_PATH)
    tool = as_langchain_tool(engine)
    result = json.loads(await tool.ainvoke({"query": "PagedAttention KV cache"}))
    assert result["sources"]
    assert "cache.md" in [s["file"] for s in result["sources"]]
    assert "PagedAttention" in result["answer"]
    assert len(engine.retriever._retrievers) == 2
    assert engine.retriever.mode == "reciprocal_rerank"


def test_bm25_finds_rare_exact_term() -> None:
    nodes = [
        TextNode(text="quasar774 special token"),
        TextNode(text="other content"),
        TextNode(text="unrelated stuff"),
    ]
    results = LexicalRetriever(nodes).retrieve("quasar774")
    assert results[0].node.text == nodes[0].text


@pytest.mark.asyncio
async def test_index_build_is_singleflight_and_client_cannot_select_paths() -> None:
    calls = []

    class Engine:
        async def aquery(self, query: str) -> str:
            return query

    async def factory(path: str) -> Engine:
        calls.append(path)
        await asyncio.sleep(0)
        return Engine()

    spec = as_mcp_tool_spec(engine_factory=factory)
    assert await asyncio.gather(spec["func"]("q1"), spec["func"]("q2")) == ["q1", "q2"]
    assert len(calls) == 1
    with pytest.raises(TypeError):
        await spec["func"]("q", docs_path="private-directory")
    with pytest.raises(ValueError):
        await spec["func"]("  ")


def test_missing_and_empty_directory_fail(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_query_engine(tmp_path / "missing")
    with pytest.raises(ValueError):
        build_query_engine(tmp_path, embed_model=DemoEmbedding(), llm=MockLLM())
